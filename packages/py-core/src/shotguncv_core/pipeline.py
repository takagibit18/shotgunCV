from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from shotguncv_agents.providers import (
    build_generator_provider,
    build_judge_provider,
)
from shotguncv_core.models import (
    ApplicationStrategy,
    CandidateProfile,
    GapMap,
    JDProfile,
    ResumeVariant,
    ScoreCard,
)
from shotguncv_core.run_config import load_run_config, snapshot_run_config
from shotguncv_core.storage import dump_json, hydrate, load_json, stage_dir
from shotguncv_evals.rules import evaluate_resume_fit


@dataclass(slots=True)
class AnalysisArtifacts:
    candidate: CandidateProfile
    jd_profiles: list[JDProfile]


@dataclass(slots=True)
class GenerationArtifacts:
    variants: list[ResumeVariant]


@dataclass(slots=True)
class EvaluationArtifacts:
    scorecards: list[ScoreCard]
    gap_maps: list[GapMap]
    summary: dict[str, object]


@dataclass(slots=True)
class PlanArtifacts:
    strategies: list[ApplicationStrategy]


def ingest_run(
    run_dir: Path,
    candidate_id: str,
    candidate_resume_path: Path,
    jd_sources: list[Path],
    config_path: Path | None = None,
) -> Path:
    ingest_directory = stage_dir(run_dir, "ingest")
    snapshot_run_config(run_dir, config_path)
    manifest = {
        "candidate_id": candidate_id,
        "candidate_resume_path": str(candidate_resume_path),
        "candidate_resume_text": candidate_resume_path.read_text(encoding="utf-8"),
        "jd_inputs": [
            {
                "source_type": "file",
                "source_value": str(source),
                "content": source.read_text(encoding="utf-8"),
            }
            for source in jd_sources
        ],
    }
    return dump_json(ingest_directory / "manifest.json", manifest)


def analyze_run(run_dir: Path) -> AnalysisArtifacts:
    load_run_config(run_dir)
    manifest = load_json(run_dir / "ingest" / "manifest.json")
    candidate = _build_candidate_profile(
        candidate_id=manifest["candidate_id"],
        candidate_resume_path=manifest["candidate_resume_path"],
        resume_text=manifest["candidate_resume_text"],
    )
    jd_profiles: list[JDProfile] = []
    for jd_input in manifest["jd_inputs"]:
        jd_profiles.extend(_parse_jd_batch(jd_input["content"], jd_input["source_type"], jd_input["source_value"]))

    analyze_directory = stage_dir(run_dir, "analyze")
    dump_json(analyze_directory / "candidate_profile.json", candidate)
    dump_json(analyze_directory / "jd_profiles.json", jd_profiles)
    return AnalysisArtifacts(candidate=candidate, jd_profiles=jd_profiles)


def generate_run(run_dir: Path) -> GenerationArtifacts:
    config = load_run_config(run_dir)
    candidate = hydrate(CandidateProfile, load_json(run_dir / "analyze" / "candidate_profile.json"))
    jd_profiles = hydrate(list[JDProfile], load_json(run_dir / "analyze" / "jd_profiles.json"))
    generator = build_generator_provider(config, stage="generate", run_dir=run_dir)

    clusters: dict[str, list[JDProfile]] = {}
    for jd in jd_profiles:
        clusters.setdefault(jd.cluster, []).append(jd)

    variants: list[ResumeVariant] = []
    for cluster, cluster_jds in clusters.items():
        variants.append(
            ResumeVariant(
                variant_id=f"variant-cluster-{cluster}",
                variant_type="cluster",
                cluster=cluster,
                target_jd_ids=[jd.jd_id for jd in cluster_jds],
                summary=generator.build_cluster_summary(cluster, candidate, cluster_jds),
                emphasized_strengths=_select_emphasized_strengths(candidate, cluster_jds[0]),
                stretch_points=_build_stretch_points(cluster_jds[0], candidate),
                source_resume_path=candidate.base_resume_path,
            )
        )

    for jd in jd_profiles:
        variants.append(
            ResumeVariant(
                variant_id=f"variant-jd-{jd.jd_id}",
                variant_type="jd-specific",
                cluster=jd.cluster,
                target_jd_ids=[jd.jd_id],
                summary=generator.build_jd_summary(jd, candidate),
                emphasized_strengths=_select_emphasized_strengths(candidate, jd),
                stretch_points=_build_stretch_points(jd, candidate),
                source_resume_path=candidate.base_resume_path,
            )
        )

    dump_json(stage_dir(run_dir, "generate") / "resume_variants.json", variants)
    return GenerationArtifacts(variants=variants)


def evaluate_run(run_dir: Path) -> EvaluationArtifacts:
    config = load_run_config(run_dir)
    candidate = hydrate(CandidateProfile, load_json(run_dir / "analyze" / "candidate_profile.json"))
    jd_profiles = hydrate(list[JDProfile], load_json(run_dir / "analyze" / "jd_profiles.json"))
    variants = hydrate(list[ResumeVariant], load_json(run_dir / "generate" / "resume_variants.json"))
    judge = build_judge_provider(config, stage="evaluate", run_dir=run_dir)

    scorecards: list[ScoreCard] = []
    gap_maps: list[GapMap] = []
    eval_summary: list[dict[str, object]] = []

    for jd in jd_profiles:
        relevant_variants = [variant for variant in variants if jd.jd_id in variant.target_jd_ids or variant.cluster == jd.cluster]
        gap_items = []
        for variant in relevant_variants:
            rule_eval = evaluate_resume_fit(jd, candidate, variant)
            judge_feedback = judge.review(jd, candidate, variant, rule_eval.overall_score)
            scorecards.append(
                ScoreCard(
                    jd_id=jd.jd_id,
                    variant_id=variant.variant_id,
                    fit_score=rule_eval.fit_score,
                    ats_score=rule_eval.ats_score,
                    evidence_score=rule_eval.evidence_score,
                    stretch_score=rule_eval.stretch_score,
                    gap_risk_score=rule_eval.gap_risk_score,
                    rewrite_cost_score=rule_eval.rewrite_cost_score,
                    overall_score=rule_eval.overall_score,
                    judge_rationale=judge_feedback.rationale,
                )
            )
            gap_items = rule_eval.gaps

        gap_map = GapMap(jd_id=jd.jd_id, candidate_id=candidate.candidate_id, items=gap_items)
        gap_maps.append(gap_map)
        eval_summary.append(
            {
                "jd_id": jd.jd_id,
                "title": jd.title,
                "top_variant_id": max(
                    (card for card in scorecards if card.jd_id == jd.jd_id),
                    key=ScoreCard.ranking_key,
                ).variant_id,
                "gap_count": len(gap_items),
            }
        )

    evaluate_directory = stage_dir(run_dir, "evaluate")
    dump_json(evaluate_directory / "scorecards.json", scorecards)
    dump_json(evaluate_directory / "gap_maps.json", gap_maps)
    dump_json(evaluate_directory / "eval_summary.json", eval_summary)
    return EvaluationArtifacts(scorecards=scorecards, gap_maps=gap_maps, summary={"items": eval_summary})


def plan_run(run_dir: Path) -> PlanArtifacts:
    load_run_config(run_dir)
    scorecards = hydrate(list[ScoreCard], load_json(run_dir / "evaluate" / "scorecards.json"))
    gap_maps = hydrate(list[GapMap], load_json(run_dir / "evaluate" / "gap_maps.json"))

    best_by_jd: dict[str, ScoreCard] = {}
    for scorecard in scorecards:
        current = best_by_jd.get(scorecard.jd_id)
        if current is None or ScoreCard.ranking_key(scorecard) > ScoreCard.ranking_key(current):
            best_by_jd[scorecard.jd_id] = scorecard

    ordered = sorted(best_by_jd.values(), key=ScoreCard.ranking_key, reverse=True)
    gap_index = {gap_map.jd_id: gap_map for gap_map in gap_maps}
    strategies: list[ApplicationStrategy] = []

    for rank, scorecard in enumerate(ordered, start=1):
        gap_map = gap_index.get(scorecard.jd_id)
        catch_up_notes = []
        if gap_map:
            for item in gap_map.items:
                catch_up_notes.extend(item.catch_up_concepts[:2])
        apply_decision = "apply" if scorecard.overall_score >= 0.7 else "stretch"
        strategies.append(
            ApplicationStrategy(
                jd_id=scorecard.jd_id,
                recommended_variant_id=scorecard.variant_id,
                priority_rank=rank,
                apply_decision=apply_decision,
                reason_summary=(
                    f"overall_score={scorecard.overall_score:.2f}, gap_risk_score={scorecard.gap_risk_score:.2f}, "
                    f"variant={scorecard.variant_id}"
                ),
                needs_jd_specific_variant="jd-" in scorecard.variant_id,
                catch_up_notes=catch_up_notes or ["No major catch-up themes detected."],
            )
        )

    dump_json(stage_dir(run_dir, "plan") / "application_strategies.json", strategies)
    return PlanArtifacts(strategies=strategies)


def report_run(run_dir: Path) -> Path:
    load_run_config(run_dir)
    candidate = hydrate(CandidateProfile, load_json(run_dir / "analyze" / "candidate_profile.json"))
    jd_profiles = hydrate(list[JDProfile], load_json(run_dir / "analyze" / "jd_profiles.json"))
    scorecards = hydrate(list[ScoreCard], load_json(run_dir / "evaluate" / "scorecards.json"))
    strategies = hydrate(list[ApplicationStrategy], load_json(run_dir / "plan" / "application_strategies.json"))
    gap_maps = hydrate(list[GapMap], load_json(run_dir / "evaluate" / "gap_maps.json"))

    jd_index = {jd.jd_id: jd for jd in jd_profiles}
    score_index = {(score.jd_id, score.variant_id): score for score in scorecards}
    gap_index = {gap_map.jd_id: gap_map for gap_map in gap_maps}

    lines = [
        "# ShotgunCV v1 Run Summary",
        "",
        f"- Candidate: `{candidate.candidate_id}`",
        f"- Run directory: `{run_dir}`",
        "",
        "## Ranked Application Strategy",
        "",
    ]

    for strategy in strategies:
        jd = jd_index[strategy.jd_id]
        scorecard = score_index[(strategy.jd_id, strategy.recommended_variant_id)]
        gap_map = gap_index.get(strategy.jd_id)
        lines.extend(
            [
                f"### {strategy.priority_rank}. {jd.title} @ {jd.company}",
                f"- Decision: `{strategy.apply_decision}`",
                f"- Recommended variant: `{strategy.recommended_variant_id}`",
                f"- overall_score: `{scorecard.overall_score:.2f}`",
                f"- judge_rationale: {scorecard.judge_rationale}",
                f"- catch-up: {', '.join(strategy.catch_up_notes)}",
            ]
        )
        if gap_map and gap_map.items:
            lines.append(f"- gap_focus: {gap_map.items[0].target_state}")
        lines.append("")

    report_path = stage_dir(run_dir, "report") / "summary.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _build_candidate_profile(candidate_id: str, candidate_resume_path: str, resume_text: str) -> CandidateProfile:
    bullet_lines = [line.strip("- ").strip() for line in resume_text.splitlines() if line.strip().startswith("-")]
    lowered = " ".join(bullet_lines).lower()
    skills = []
    for keyword, label in (
        ("python", "Python"),
        ("llm", "LLM workflows"),
        ("resume", "Resume evaluation"),
        ("product", "Product collaboration"),
    ):
        if keyword in lowered:
            skills.append(label)

    return CandidateProfile(
        candidate_id=candidate_id,
        base_resume_path=candidate_resume_path,
        experiences=bullet_lines,
        projects=[line for line in bullet_lines if "prototype" in line.lower() or "tool" in line.lower()],
        skills=skills or ["AI workflow delivery"],
        industry_tags=["AI tooling", "Resume ops"],
        strengths=bullet_lines[:2] or ["Structured AI workflow delivery"],
        constraints=["No explicit production ML platform ownership yet"],
        preferences=["Product-oriented AI roles"],
    )


def _parse_jd_batch(content: str, source_type: str, source_value: str) -> list[JDProfile]:
    blocks = [block.strip() for block in content.split("=== JD ===") if block.strip()]
    profiles: list[JDProfile] = []
    for index, block in enumerate(blocks, start=1):
        title = _extract_header(block, "Title")
        company = _extract_header(block, "Company")
        body_lines = _extract_body_lines(block)
        keyword_candidates = _extract_keywords(" ".join(body_lines))
        bonuses = [line.replace("Bonus for ", "").strip() for line in body_lines if "bonus" in line.lower()]
        profiles.append(
            JDProfile(
                jd_id=f"jd-{index:03d}",
                title=title,
                company=company,
                cluster=_classify_cluster(title, body_lines),
                responsibilities=body_lines,
                requirements=body_lines[:2],
                keywords=keyword_candidates,
                seniority="mid",
                bonuses=bonuses,
                risk_signals=_build_risk_signals(body_lines),
                source_type=source_type,
                source_value=source_value,
            )
        )
    return profiles


def _extract_header(block: str, label: str) -> str:
    match = re.search(rf"{label}:\s*(.+)", block)
    return match.group(1).strip() if match else ""


def _extract_body_lines(block: str) -> list[str]:
    if "Body:" not in block:
        return []
    body = block.split("Body:", maxsplit=1)[1]
    return [line.strip("- ").strip() for line in body.splitlines() if line.strip().startswith("-")]


def _extract_keywords(text: str) -> list[str]:
    keyword_map = [
        ("evaluation", "evaluation"),
        ("ranking", "ranking"),
        ("python", "python"),
        ("prompt", "prompt engineering"),
        ("product", "product collaboration"),
        ("automation", "automation"),
        ("metrics", "metrics"),
        ("experimentation", "experimentation"),
        ("llm", "llm"),
    ]
    lowered = text.lower()
    keywords = [label for needle, label in keyword_map if needle in lowered]
    return keywords[:5] or ["python", "ai workflows"]


def _classify_cluster(title: str, body_lines: list[str]) -> str:
    lowered = f"{title} {' '.join(body_lines)}".lower()
    if "product" in lowered or "evaluation" in lowered or "prompt" in lowered:
        return "ai-product"
    return "ai-operations"


def _build_risk_signals(body_lines: list[str]) -> list[str]:
    signals = []
    lowered = " ".join(body_lines).lower()
    if "metrics" in lowered or "experimentation" in lowered:
        signals.append("Requires metrics storytelling")
    if "prompt" in lowered:
        signals.append("Prompt quality will be probed")
    return signals


def _select_emphasized_strengths(candidate: CandidateProfile, jd: JDProfile) -> list[str]:
    strengths = []
    for keyword in jd.keywords:
        for candidate_line in candidate.experiences + candidate.skills:
            if keyword.split()[0] in candidate_line.lower():
                strengths.append(candidate_line)
                break
    return strengths[:3] or candidate.strengths[:2]


def _build_stretch_points(jd: JDProfile, candidate: CandidateProfile) -> list[str]:
    candidate_text = " ".join(candidate.experiences + candidate.projects + candidate.skills).lower()
    stretch_points = [keyword for keyword in jd.keywords if keyword.lower() not in candidate_text]
    return stretch_points[:3] or [jd.keywords[-1]]

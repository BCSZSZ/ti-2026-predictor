from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from test_fantasy_scenarios import _banner as scenario_banner
from test_fantasy_scenarios import _build_foundation

from ti_predictor.fantasy.roll import (
    BannerState,
    EmblemState,
    GroupRollState,
    RollOffer,
    build_group_roll_rules,
)
from ti_predictor.fantasy.solver import (
    POSITIONED_CONFIGURATION_COUNT,
    BranchCappedRollSolver,
    ExactFixedStatConfigurationEvaluator,
    FixedStatConfigurationValues,
    ObjectiveEstimate,
    SynergyPotentialTable,
    banner_from_configuration,
    build_synergy_potential_table,
    configuration_digits,
    configuration_index,
    exact_fixed_offer_oracle,
    hamming_three_neighbor_indexes,
    load_solver_policy,
)
from ti_predictor.fantasy.solver_validation import (
    SolverSessionKey,
    SolverSessionResult,
    common_situations_by_case,
    coverage_cases_from_p4,
    subset_solver_scenarios,
    summarize_solver_validation,
)
from ti_predictor.fantasy.valuation import (
    MatchedOutcome,
    RiskConfiguration,
    evaluate_banner_teams,
    match_one_banner,
)
from ti_predictor.rules import _inspect_fantasy_crafting


@pytest.fixture
def roll_rules(rules_payload):
    fixture = Path(__file__).parent / "fixtures/fantasy_roll_rules_2026.vdata"
    client_roll = _inspect_fantasy_crafting(fixture.read_text(encoding="utf-8"))
    return build_group_roll_rules(rules_payload, client_roll)


def _state(rules, *, remaining: int = 1) -> GroupRollState:
    banners = []
    for role in rules.group_roles:
        colors = rules.colors_for(role)[:3]
        banners.append(
            BannerState(
                role=role,
                emblems=tuple(
                    EmblemState(
                        stat_id=rules.stats_for(color)[slot],
                        quality_tier=slot + 1,
                        trait_id=rules.traits[slot],
                    )
                    for slot, color in enumerate(colors)
                ),
            )
        )
    return GroupRollState(
        banners=tuple(banners),
        offer=RollOffer((23, 24, 25)),
        remaining_rolls=remaining,
    )


def test_solver_policy_freezes_models_risk_budget_and_failure_semantics(project_paths) -> None:
    policy = load_solver_policy(
        project_paths.config / "models" / "fantasy-group-branch-capped-solver-v1.json"
    )

    assert policy.transition_models == (
        "client-weight-primary-v1",
        "flattened-weights-v1",
        "sharpened-weights-v1",
    )
    assert policy.mean_retention_epsilons == (0.0, 0.01, 0.02, 0.05)
    assert policy.synergy_potential.positioned_configuration_count == 15_625
    assert policy.synergy_potential.simulated_stat_change_potential == "zero_until_observed_replan"
    assert policy.decision_budget.unresolved_fallback == "rate_agnostic_safety"
    assert policy.full_planner_auto_activation is False


def test_configuration_index_round_trip_covers_all_positioned_states(roll_rules) -> None:
    stats = tuple(roll_rules.stats_for(color)[0] for color in roll_rules.colors_for("core")[:3])
    observed = set()
    for index in (0, 1, 4, 5, 137, 7_812, 15_624):
        banner = banner_from_configuration("core", stats, roll_rules.traits, index)
        assert configuration_index(banner, roll_rules.traits) == index
        observed.add(tuple(configuration_digits()[index]))

    assert configuration_digits().shape == (15_625, 6)
    assert len(observed) == 7
    assert tuple(configuration_digits()[0]) == (0, 0, 0, 0, 0, 0)
    assert tuple(configuration_digits()[-1]) == (4, 4, 4, 4, 4, 4)


def test_hamming_three_lookup_is_complete_unique_and_never_exceeds_radius() -> None:
    neighbors = hamming_three_neighbor_indexes()

    assert neighbors.shape == (15_625, 1_545)
    for index in (0, 137, 7_812, 15_624):
        values = neighbors[index]
        assert len(np.unique(values)) == 1_545
        distances = np.count_nonzero(
            configuration_digits()[values] != configuration_digits()[index],
            axis=1,
        )
        assert int(distances.max()) == 3
        assert index in values


def test_synergy_table_uses_epsilon_then_cvar_with_deterministic_ties() -> None:
    count = POSITIONED_CONFIGURATION_COUNT
    means = np.zeros(count, dtype=float)
    cvars = np.zeros(count, dtype=float)
    means[0] = 100.0
    means[1] = 99.0
    cvars[0] = 20.0
    cvars[1] = 80.0
    values = FixedStatConfigurationValues(
        role="core",
        stat_ids=("a", "b", "c"),
        trait_order=("friendly", "benevolent", "vampiric", "unique", "fractal"),
        selected_means=means,
        selected_cvars=cvars,
        maximum_means=means,
        selected_team_ids=np.ones(count, dtype=np.int64),
        scenario_sha256="scenario",
        risk_sha256="risk",
    )

    strict = build_synergy_potential_table(values, epsilon=0.0)
    tolerant = build_synergy_potential_table(values, epsilon=0.02)

    assert int(strict.selected_neighbor_indexes[0]) == 0
    assert int(tolerant.selected_neighbor_indexes[0]) == 1
    assert strict.semantic_hash != tolerant.semantic_hash


def test_vectorized_fixed_stat_table_matches_p3_terminal_arithmetic(
    project_paths,
    rules_payload,
    roll_rules,
) -> None:
    _, _, pools, scenarios, _, _, _ = _build_foundation(project_paths, rules_payload)
    evaluator = ExactFixedStatConfigurationEvaluator(
        pools,
        scenarios,
        rules_payload,
        roll_rules,
        chunk_size=257,
    )
    template = scenario_banner("core")
    risk = RiskConfiguration(mean_retention_epsilon=0.02, cvar_alpha=0.1)

    table = evaluator.evaluate(template, risk)

    assert table.selected_means.shape == (15_625,)
    assert table.selected_cvars.shape == (15_625,)
    for index in (0, 137, 15_624):
        banner = banner_from_configuration(
            "core",
            table.stat_ids,
            roll_rules.traits,
            index,
        )
        matched = match_one_banner(
            evaluate_banner_teams(pools, scenarios, banner, rules_payload),
            risk,
        )
        assert table.selected_means[index] == pytest.approx(matched.summary["mean"])
        assert table.selected_cvars[index] == pytest.approx(matched.summary["cvar"])
        assert table.selected_team_ids[index] == matched.selected_team_ids[0]


class _ToyTerminal:
    def __init__(self) -> None:
        self.scenario_sha256 = "toy-scenarios"

    @staticmethod
    def _score(banners: tuple[BannerState, ...]) -> float:
        return float(sum(emblem.quality_tier for banner in banners for emblem in banner.emblems))

    def matched_group(
        self,
        banners: tuple[BannerState, ...],
        risk: RiskConfiguration,
    ) -> MatchedOutcome:
        score = self._score(banners)
        outcomes = np.asarray([score - 1.0, score, score + 1.0, score], dtype=float)
        return MatchedOutcome(
            scope="group",
            selected_team_ids=(1, 1, 1),
            scenario_sha256=self.scenario_sha256,
            risk_sha256=risk.semantic_hash,
            outcomes=outcomes,
            maximum_mean=score,
            summary={
                "mean": float(outcomes.mean()),
                "cvar": float(outcomes.min()),
                "p10": float(np.quantile(outcomes, 0.1)),
                "p50": float(np.quantile(outcomes, 0.5)),
                "p90": float(np.quantile(outcomes, 0.9)),
                "minimum": float(outcomes.min()),
                "maximum": float(outcomes.max()),
            },
        )

    def banner_objective(self, banner: BannerState, risk: RiskConfiguration) -> ObjectiveEstimate:
        del risk
        score = float(sum(emblem.quality_tier for emblem in banner.emblems))
        return ObjectiveEstimate(mean=score, cvar=score - 1.0)


class _ToyPotentialProvider:
    def __init__(self, trait_order: tuple[str, ...]) -> None:
        self.trait_order = trait_order
        self.cache: dict[tuple[str, tuple[str, ...], str], SynergyPotentialTable] = {}

    def __call__(
        self,
        banner: BannerState,
        risk: RiskConfiguration,
    ) -> SynergyPotentialTable:
        stats = tuple(emblem.stat_id for emblem in banner.emblems)
        key = (banner.role, stats, risk.semantic_hash)
        if key not in self.cache:
            digits = configuration_digits()
            means = digits[:, :3].sum(axis=1).astype(float) + 3.0
            values = FixedStatConfigurationValues(
                role=banner.role,
                stat_ids=stats,
                trait_order=self.trait_order,
                selected_means=means,
                selected_cvars=means - 1.0,
                maximum_means=means,
                selected_team_ids=np.ones(POSITIONED_CONFIGURATION_COUNT, dtype=np.int64),
                scenario_sha256="toy-scenarios",
                risk_sha256=risk.semantic_hash,
            )
            self.cache[key] = SynergyPotentialTable(
                values=values,
                epsilon=risk.mean_retention_epsilon,
                maximum_attribute_differences=3,
                selected_neighbor_indexes=np.arange(
                    POSITIONED_CONFIGURATION_COUNT,
                    dtype=np.uint16,
                ),
            )
        return self.cache[key]


def test_solver_uses_fresh_confirmation_is_reproducible_and_falls_back_when_unresolved(
    project_paths,
    roll_rules,
) -> None:
    policy = load_solver_policy(
        project_paths.config / "models" / "fantasy-group-branch-capped-solver-v1.json"
    )
    terminal = _ToyTerminal()
    solver = BranchCappedRollSolver(
        roll_rules,
        terminal,
        _ToyPotentialProvider(roll_rules.traits),
        policy,
    )
    state = _state(roll_rules, remaining=1)

    first = solver.decide(state, model_id="client-weight-primary-v1", epsilon=0.02)
    repeated = solver.decide(state, model_id="client-weight-primary-v1", epsilon=0.02)

    assert first == repeated
    assert all(len(item.scores) == 4 for item in first.screening)
    assert all(len(item.scores) == 12 for item in first.confirmation)
    assert first.approximate_not_globally_optimal is True
    if not first.resolved:
        assert first.executed_action != first.preferred_action or first.resolution_reason.startswith(
            "confirmation cannot"
        )


def test_short_horizon_oracle_is_exact_only_for_the_declared_offer_schedule(roll_rules) -> None:
    terminal = _ToyTerminal()
    state = _state(roll_rules, remaining=2)
    risk = RiskConfiguration(mean_retention_epsilon=0.0, cvar_alpha=0.1)

    result = exact_fixed_offer_oracle(
        state,
        (RollOffer((23, 24, 25)), RollOffer((23, 24, 25))),
        rules=roll_rules,
        terminal=terminal,
        model_id="client-weight-primary-v1",
        risk=risk,
    )

    assert result.selected_action is not None
    assert result.exact_for_declared_condition is True
    assert result.conditional_offer_schedule == ((23, 24, 25), (23, 24, 25))
    assert result.distribution.weights.sum() == pytest.approx(1.0)
    assert result.distribution.mean == max(item.mean for item in result.action_values)


def _p4_coverage_payload(roll_rules) -> dict:
    state = _state(roll_rules, remaining=40)
    cases = []
    common = []
    for index in range(1, 10):
        case_id = f"coverage-{index:02d}"
        cases.append(
            {
                "case_id": case_id,
                "offer_operation_ids": list(state.offer.operation_ids),
                "roles": [
                    {
                        "role": banner.role,
                        "stat_readiness": ("low", "middle", "high")[(index - 1) % 3],
                        "configuration_readiness": ("low", "middle", "high")[(index - 1) // 3],
                        "emblems": [
                            {
                                "stat_id": emblem.stat_id,
                                "quality_tier": emblem.quality_tier,
                                "trait_id": emblem.trait_id,
                            }
                            for emblem in banner.emblems
                        ],
                    }
                    for banner in state.banners
                ],
            }
        )
        common.append(
            {
                "case_id": case_id,
                "edition": "primary-model",
                "situation": f"PM{index:02d}",
            }
        )
    return {
        "coverage_suite": cases,
        "common_situation_conditional_loss": common,
    }


def test_p5_reuses_frozen_p4_coverage_and_common_situation_identities(roll_rules) -> None:
    evidence = _p4_coverage_payload(roll_rules)

    cases = coverage_cases_from_p4(evidence)
    situations = common_situations_by_case(evidence)

    assert len(cases) == 9
    assert cases[0].state.remaining_rolls == 40
    assert cases[0].state.banners == _state(roll_rules, remaining=40).banners
    assert situations["coverage-01"] == ("primary-model:PM01",)


def test_p5_scenario_subset_is_fixed_paired_and_seed_sensitive(project_paths, rules_payload) -> None:
    _, _, _, scenarios, _, _, _ = _build_foundation(project_paths, rules_payload)

    first = subset_solver_scenarios(scenarios, count=4, seed=81)
    repeated = subset_solver_scenarios(scenarios, count=4, seed=81)
    changed = subset_solver_scenarios(scenarios, count=4, seed=82)

    assert first.semantic_hash == repeated.semantic_hash
    assert first.semantic_hash != changed.semantic_hash
    assert all(item.block_indexes.shape[0] == 4 for item in first.draws)


def test_incomplete_or_conditional_evidence_cannot_pass_p5_gate(project_paths) -> None:
    policy = load_solver_policy(
        project_paths.config / "models" / "fantasy-group-branch-capped-solver-v1.json"
    )
    key = SolverSessionKey(
        model_id="client-weight-primary-v1",
        epsilon=0.0,
        case_id="coverage-01",
        replicate=0,
    )
    sessions = tuple(
        SolverSessionResult(
            key=key,
            policy_id=policy_id,
            score=100.0,
            selected_team_ids=(1, 2, 3),
            unresolved_decisions=1 if policy_id == "branch_capped" else 0,
            full_horizon_equivalent_paths=1.0 if policy_id == "branch_capped" else 0.0,
            situations=("primary-model:PM01",),
            action_sequence=("refresh",),
        )
        for policy_id in ("branch_capped", "one_step_greedy", "rate_agnostic_safety")
    )

    payload = summarize_solver_validation(
        sessions,
        policy=policy,
        expected_solver_session_count=2,
        runtime_seconds=10.0,
        oracle={"gate_pass": False},
    )

    assert payload["gate"]["validation_complete"] is False
    assert payload["gate"]["oracle_regret_pass"] is False
    assert payload["gate"]["common_unresolved_pass"] is False
    assert payload["gate"]["p5_status"] == "failed-escalation-review-required"

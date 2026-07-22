# -*- coding: utf-8 -*-
from dataclasses import replace

from sim_v12_layered import (
    ALL_TECHS,
    Config,
    ORES,
    State,
    buy_available_tech,
    controlled_factor,
    extrapolate_stable_cycles,
    record_exact_cycle,
    run,
    run_cycle,
)


def exact_state(target: int) -> State:
    cfg = replace(Config(), second_order_exponent=1, exact_cycle_limit=128)
    state = State()
    while state.resets < target:
        buy_available_tech(state)
        record_exact_cycle(state, run_cycle(state, cfg))
    state.won = True
    return state


def test_first_three_runs_are_complete_manual_replays():
    state = run()
    first = state.history[:3]
    assert len(first) == 3
    assert all(row["manual_actions"] >= 8 for row in first)
    assert all(row["techs"] == [] for row in first)


def test_reset_clears_run_resources_and_rewards_one_shard():
    state = run()
    assert all(row["reward"] == 1 for row in state.history)
    assert all(all(row["cleared"].values()) for row in state.history)
    assert all(max(row["levels_before_reset"]) > 0 for row in state.history)


def test_permanent_tech_reaches_fixed_state_before_extrapolation():
    state = run()
    assert state.techs == set(ALL_TECHS)
    assert state.history[-1]["techs"] == sorted(ALL_TECHS)
    assert state.exact_cycles == len(state.history) == 13
    assert state.extrapolation["cycles"] == Config().second_order_need - 13


def test_astronomical_target_is_not_iterated():
    cfg = Config()
    state = run(cfg)
    assert cfg.second_order_need == 10**308
    assert state.resets == cfg.second_order_need
    assert state.exact_cycles < cfg.exact_cycle_limit
    assert (
        state.extrapolation["formula"]
        == "total = exact_prefix + stable_cycle_sample * N"
    )


def test_extrapolation_matches_small_scale_round_by_round():
    cfg = replace(Config(), second_order_exponent=2, exact_cycle_limit=128)
    exact = run(cfg, force_exact=True)
    projected = run(cfg)
    assert projected.resets == exact.resets == 100
    assert projected.day == exact.day
    assert projected.shards == exact.shards
    assert sum(projected.cycle_manual) + projected.extrapolation[
        "manual_actions"
    ] == sum(exact.cycle_manual)


def test_batch_formula_matches_repeated_stable_cycle():
    cfg = replace(Config(), second_order_exponent=2, exact_cycle_limit=128)
    prefix = State(resets=20, shards=8, techs=set(ALL_TECHS))
    sample = run_cycle(prefix, cfg)
    projected = State(resets=20, shards=8, techs=set(ALL_TECHS))
    extrapolate_stable_cycles(projected, cfg, sample, 7)
    repeated = State(resets=20, shards=8, techs=set(ALL_TECHS))
    for _ in range(7):
        record_exact_cycle(repeated, run_cycle(repeated, cfg))
    assert (projected.resets, projected.day, projected.shards) == (
        repeated.resets,
        repeated.day,
        repeated.shards,
    )
    assert projected.extrapolation["mineral_actual"] == tuple(
        value * 7 for value in sample.mineral_actual
    )


def test_mineral_noise_is_bounded_deterministic_and_zero_mean_per_block():
    cfg = Config()
    factors = [controlled_factor(0, pulse, cfg.mineral_noise) for pulse in range(4)]
    assert factors == [
        controlled_factor(0, pulse, cfg.mineral_noise) for pulse in range(4)
    ]
    assert max(abs(value - 1.0) for value in factors) <= cfg.mineral_noise + 1e-12
    assert abs(sum(factors) / len(factors) - 1.0) <= 1e-12
    state = run(cfg)
    expected = state.stable_sample["mineral_expected"]
    actual = state.stable_sample["mineral_actual"]
    assert all(
        abs(a - e) <= e * cfg.mineral_noise for e, a in zip(expected, actual) if e
    )


def test_currency_is_exclusive_and_conserved():
    state = run()
    assert state.spent_shards == 12
    assert state.shards + state.spent_shards == state.resets
    assert sum(row["reward"] for row in state.history) == state.exact_cycles
    assert state.extrapolation["rewards"] + state.exact_cycles == state.resets

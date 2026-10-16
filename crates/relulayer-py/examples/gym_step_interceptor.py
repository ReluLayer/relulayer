"""Drop-in ReluLayer safety wrapper for an RL env.step() loop."""

from relulayer import Governor


def main() -> None:
    gov = Governor(min_bound=-12.0, max_bound=12.0)
    env = make_env()  # noqa: F821 - user-supplied gym/mujoco environment
    policy = load_policy()  # noqa: F821 - user-supplied trained policy

    obs = env.reset()
    for _ in range(1000):
        action = policy(obs)              # unconstrained policy output
        safe_action = gov.project(action) # hard real-time safety governor
        obs, reward, done, info = env.step(safe_action)
        if done:
            obs = env.reset()


if __name__ == "__main__":
    main()

import unittest

from freiren_quiet.policy import ThermalPolicy


class PolicyTests(unittest.TestCase):
    def test_brief_spike_does_not_change_cap(self):
        policy = ThermalPolicy()
        self.assertEqual(policy.decide(70).cap, 60)
        self.assertEqual(policy.decide(64).cap, 60)
        self.assertEqual(policy.decide(70).cap, 60)

    def test_sustained_heat_steps_down_but_never_below_floor(self):
        policy = ThermalPolicy()
        self.assertEqual(policy.decide(70).cap, 60)
        self.assertEqual(policy.decide(70).cap, 55)
        for _ in range(30):
            decision = policy.decide(70)
        self.assertEqual(decision.cap, 40)

    def test_recovery_is_slow_and_bounded(self):
        policy = ThermalPolicy()
        policy.decide(80)
        for _ in range(5):
            self.assertEqual(policy.decide(55).cap, 40)
        self.assertEqual(policy.decide(55).cap, 45)
        for _ in range(100):
            decision = policy.decide(55)
        self.assertEqual(decision.cap, 75)

    def test_emergency_overrides_performance_and_needs_cooldown(self):
        policy = ThermalPolicy("performance")
        decision = policy.decide(86)
        self.assertEqual((decision.cap, decision.no_turbo), (25, 1))
        for _ in range(5):
            self.assertEqual(policy.decide(74).cap, 25)
        self.assertEqual(policy.decide(76).cap, 25)
        for _ in range(5):
            self.assertEqual(policy.decide(74).cap, 25)
        self.assertEqual(policy.decide(74).cap, 100)

    def test_missing_or_invalid_sensors_never_unlock_performance(self):
        for temperature in (None, float("nan"), float("inf"), -10, 0, 125):
            with self.subTest(temperature=temperature):
                decision = ThermalPolicy("performance").decide(temperature)
                self.assertEqual((decision.cap, decision.no_turbo), (40, 1))

    def test_dead_band_does_not_oscillate(self):
        policy = ThermalPolicy()
        for temperature in [61, 65, 63, 66] * 20:
            self.assertEqual(policy.decide(temperature).cap, 60)

    def test_restore_never_requests_changes_even_when_hot(self):
        self.assertIsNone(ThermalPolicy("restore").decide(95))

    def test_reject_invalid_targets_and_modes(self):
        for target in (True, 57, 76, "64", 64.0):
            with self.assertRaises(ValueError):
                ThermalPolicy(target=target)
        with self.assertRaises(ValueError):
            ThermalPolicy(mode="unknown")

    def test_fixed_profiles_are_explicit(self):
        self.assertEqual(ThermalPolicy("quiet").decide(65).cap, 60)
        self.assertEqual(ThermalPolicy("balanced").decide(65).no_turbo, 1)
        self.assertEqual(ThermalPolicy("performance").decide(65).no_turbo, 0)


if __name__ == "__main__":
    unittest.main()

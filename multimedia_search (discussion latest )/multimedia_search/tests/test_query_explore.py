import unittest

from multimedia_search.utils.query_explore import build_query_exploration_groups


class TestQueryExplore(unittest.TestCase):
    def _flatten(self, groups):
        return [
            query
            for group in groups
            for query in group["queries"]
        ]

    def test_dog_query_has_type_place_body_and_action_suggestions(self):
        groups = build_query_exploration_groups("dog")
        flat = self._flatten(groups)

        self.assertIn("golden retriever dog", flat)
        self.assertIn("labrador dog", flat)
        self.assertIn("dog in park", flat)
        self.assertIn("dog in home", flat)
        self.assertIn("dog face", flat)
        self.assertIn("dog ears", flat)
        self.assertIn("dog running", flat)

    def test_vehicle_query_has_vehicle_specific_suggestions(self):
        groups = build_query_exploration_groups("car")
        flat = self._flatten(groups)

        self.assertIn("sports car", flat)
        self.assertIn("electric car", flat)
        self.assertIn("car on road", flat)
        self.assertIn("car headlights", flat)
        self.assertIn("car interior", flat)

    def test_device_query_has_device_specific_suggestions(self):
        groups = build_query_exploration_groups("camera")
        flat = self._flatten(groups)

        self.assertIn("digital camera", flat)
        self.assertIn("camera close up", flat)
        self.assertIn("camera on desk", flat)
        self.assertIn("camera lens", flat)

    def test_plant_query_has_plant_specific_suggestions(self):
        groups = build_query_exploration_groups("flower")
        flat = self._flatten(groups)

        self.assertIn("red flower", flat)
        self.assertIn("flower in garden", flat)
        self.assertIn("flower petals", flat)
        self.assertIn("flower close up", flat)

    def test_unknown_query_gets_generic_image_exploration_suggestions(self):
        groups = build_query_exploration_groups("backpack")
        flat = self._flatten(groups)

        self.assertIn("backpack close up", flat)
        self.assertIn("backpack side view", flat)
        self.assertIn("backpack indoors", flat)
        self.assertIn("backpack outdoors", flat)
        self.assertIn("backpack details", flat)

    def test_multiword_query_keeps_the_full_query_in_templates(self):
        groups = build_query_exploration_groups("black dog")
        flat = self._flatten(groups)

        self.assertIn("black dog in park", flat)
        self.assertIn("black dog face", flat)
        self.assertIn("black dog running", flat)

    def test_empty_query_returns_no_suggestions(self):
        self.assertEqual(build_query_exploration_groups(""), [])
        self.assertEqual(build_query_exploration_groups("   "), [])

    def test_original_query_is_not_repeated_as_a_chip(self):
        groups = build_query_exploration_groups("dog")
        flat = self._flatten(groups)

        self.assertNotIn("dog", flat)


if __name__ == "__main__":
    unittest.main()
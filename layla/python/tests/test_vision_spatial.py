import unittest

from avishkar_layla.vision.spatial import BoundingBox, distance, iou, nearest, overlaps, relative_position


class TestBoundingBox(unittest.TestCase):
    def test_rejects_inverted_box(self):
        with self.assertRaises(ValueError):
            BoundingBox(x0=10, y0=10, x1=5, y1=20)

    def test_center_width_height_area(self):
        box = BoundingBox(x0=0, y0=0, x1=10, y1=20)
        self.assertEqual(box.center, (5.0, 10.0))
        self.assertEqual(box.width, 10)
        self.assertEqual(box.height, 20)
        self.assertEqual(box.area, 200)


class TestOverlapAndIoU(unittest.TestCase):
    def test_disjoint_boxes_do_not_overlap(self):
        a = BoundingBox(0, 0, 10, 10)
        b = BoundingBox(20, 20, 30, 30)
        self.assertFalse(overlaps(a, b))
        self.assertEqual(iou(a, b), 0.0)

    def test_identical_boxes_have_iou_one(self):
        a = BoundingBox(0, 0, 10, 10)
        b = BoundingBox(0, 0, 10, 10)
        self.assertTrue(overlaps(a, b))
        self.assertAlmostEqual(iou(a, b), 1.0)

    def test_partial_overlap_iou_between_zero_and_one(self):
        a = BoundingBox(0, 0, 10, 10)
        b = BoundingBox(5, 5, 15, 15)
        value = iou(a, b)
        self.assertGreater(value, 0.0)
        self.assertLess(value, 1.0)


class TestRelativePosition(unittest.TestCase):
    def test_right_of(self):
        a = BoundingBox(100, 0, 110, 10)
        b = BoundingBox(0, 0, 10, 10)
        self.assertEqual(relative_position(a, b), "right_of")

    def test_left_of(self):
        a = BoundingBox(0, 0, 10, 10)
        b = BoundingBox(100, 0, 110, 10)
        self.assertEqual(relative_position(a, b), "left_of")

    def test_below(self):
        a = BoundingBox(0, 100, 10, 110)
        b = BoundingBox(0, 0, 10, 10)
        self.assertEqual(relative_position(a, b), "below")

    def test_above(self):
        a = BoundingBox(0, 0, 10, 10)
        b = BoundingBox(0, 100, 10, 110)
        self.assertEqual(relative_position(a, b), "above")

    def test_overlapping_boxes_report_overlapping_not_a_direction(self):
        a = BoundingBox(0, 0, 20, 20)
        b = BoundingBox(5, 5, 25, 25)
        self.assertEqual(relative_position(a, b), "overlapping")


class TestNearest(unittest.TestCase):
    def test_finds_the_real_closest_candidate(self):
        target = BoundingBox(0, 0, 10, 10)
        near = BoundingBox(20, 0, 30, 10)
        far = BoundingBox(1000, 1000, 1010, 1010)
        self.assertEqual(nearest(target, [far, near]), near)

    def test_empty_candidates_returns_none(self):
        target = BoundingBox(0, 0, 10, 10)
        self.assertIsNone(nearest(target, []))

    def test_distance_is_symmetric(self):
        a = BoundingBox(0, 0, 10, 10)
        b = BoundingBox(100, 100, 110, 110)
        self.assertAlmostEqual(distance(a, b), distance(b, a))


if __name__ == "__main__":
    unittest.main()

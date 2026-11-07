import unittest
from src.greeting import greet


class GreetingTests(unittest.TestCase):
    def test_greet_with_normal_name(self):
        """Test greet function with a normal name."""
        result = greet("Alice")
        self.assertEqual(result, "Hello, Alice!")
        
    def test_greet_with_empty_string(self):
        """Test greet function with empty string."""
        result = greet("")
        self.assertEqual(result, "Hello!")


if __name__ == "__main__":
    unittest.main()
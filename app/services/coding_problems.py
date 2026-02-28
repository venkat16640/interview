"""
Enhanced AI Service - Professional Coding Problems
Generates LeetCode/HackerRank-style coding problems via Google Gemini.
"""
import json
import random
import re

import google.generativeai as genai
from flask import current_app


# ─────────────────────────────────────────────────────────────────────────────
# Gemini helper
# ─────────────────────────────────────────────────────────────────────────────

def get_gemini_model():
    """Return a configured Gemini GenerativeModel."""
    api_key = current_app.config.get('GEMINI_API_KEY')
    if not api_key or api_key == 'your-api-key-here':
        raise RuntimeError("GEMINI_API_KEY is not set in .env")
    genai.configure(api_key=api_key)
    # gemini-1.5-flash is fast, cheap, and widely available
    return genai.GenerativeModel('gemini-1.5-pro')

# ─────────────────────────────────────────────────────────────────────────────
# Main public function
# ─────────────────────────────────────────────────────────────────────────────

def generate_coding_problem(resume_data, difficulty='medium', previous_questions=None):
    """
    Generate a professional, LeetCode-style coding problem using Gemini.

    Args:
        resume_data       : parsed resume dict (may contain 'skills' list)
        difficulty        : 'easy' | 'medium' | 'hard'
        previous_questions: list of previously asked question *strings* —
                            used only to avoid repeats.

    Returns a dict with keys:
        title, difficulty, description, examples, constraints,
        function_name, starter_code, test_cases
    """
    if previous_questions is None:
        previous_questions = []

    # Detect the candidate's preferred programming language from resume
    skills = resume_data.get('skills', [])
    lang_map = {
        'python': 'Python', 'java': 'Java',
        'javascript': 'JavaScript', 'js': 'JavaScript',
        'c++': 'C++', 'cpp': 'C++', 'c#': 'C#'
    }
    lang = 'Python'
    for skill in skills:
        key = skill.lower().strip()
        if key in lang_map:
            lang = lang_map[key]
            break

    # Build a readable avoid-list (first 60 chars of recent question texts)
    avoid_titles = [str(q)[:60] for q in previous_questions[-3:]] if previous_questions else []
    avoid_str = ', '.join(avoid_titles) if avoid_titles else 'None'

    difficulty_cap = difficulty.capitalize()

    prompt = f"""You are a senior software engineer creating a coding interview problem.

Generate ONE {difficulty_cap}-difficulty coding problem for {lang}, in the style of LeetCode or HackerRank.

STRICTLY return ONLY a single valid JSON object — no markdown, no code fences, no extra text.

Required JSON structure:
{{
  "title": "Short problem title (e.g. 'Two Sum')",
  "difficulty": "{difficulty_cap}",
  "description": "Full plain-text problem description. Explain the task clearly with 2-3 sentences. No HTML tags.",
  "examples": [
    {{
      "input": "Example input as a readable string",
      "output": "Expected output as a readable string",
      "explanation": "Why this output is correct"
    }}
  ],
  "constraints": [
    "1 <= n <= 10^5",
    "Values are in range [-10^4, 10^4]"
  ],
  "function_name": "camelCase function name matching the problem",
  "starter_code": "def functionName(param1, param2):\\n    # Write your solution here\\n    pass",
  "test_cases": [
    {{"input": [/* actual Python list of args, one per param */], "output": /* expected return value */}},
    {{"input": [/* second test */], "output": /* expected */}},
    {{"input": [/* third test */], "output": /* expected */}}
  ]
}}

Rules:
- The problem must be solvable in {lang}.
- starter_code must use Python syntax (we run it server-side in Python).
- function_name must match the def in starter_code exactly.
- test_cases[i].input is a list of positional arguments (one item per parameter).
- test_cases[i].output is the exact expected return value.
- Avoid problems similar to: {avoid_str}
- Make the problem original and interesting — not just "Two Sum" or "FizzBuzz".
"""

    try:
        model = get_gemini_model()
        response = model.generate_content(prompt)
        raw = response.text.strip()

        # Strip markdown fences if Gemini wraps the JSON anyway
        raw = re.sub(r'^```[a-z]*\s*', '', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()

        problem = json.loads(raw)

        # Validate required keys
        required = {'title', 'description', 'examples', 'constraints',
                    'function_name', 'starter_code', 'test_cases'}
        if not required.issubset(problem.keys()):
            raise ValueError(f"Missing keys in response: {required - problem.keys()}")

        # Normalise difficulty field
        problem['difficulty'] = difficulty_cap
        return problem

    except Exception as exc:
        print(f"[coding_problems] Gemini generation failed: {exc}. Using fallback.")
        return get_fallback_coding_problem(difficulty)


# ─────────────────────────────────────────────────────────────────────────────
# Rich fallback problem bank  (Easy × 3, Medium × 3, Hard × 2)
# ─────────────────────────────────────────────────────────────────────────────

_FALLBACK_PROBLEMS = {
    'easy': [
        {
            "title": "Two Sum",
            "difficulty": "Easy",
            "function_name": "twoSum",
            "description": (
                "Given an array of integers `nums` and an integer `target`, "
                "return the indices of the two numbers that add up to `target`. "
                "Each input has exactly one solution; you may not use the same element twice."
            ),
            "examples": [
                {
                    "input": "nums = [2, 7, 11, 15], target = 9",
                    "output": "[0, 1]",
                    "explanation": "nums[0] + nums[1] == 9"
                }
            ],
            "constraints": [
                "2 <= nums.length <= 10^4",
                "-10^9 <= nums[i] <= 10^9",
                "Only one valid answer exists."
            ],
            "starter_code": (
                "def twoSum(nums, target):\n"
                "    \"\"\"\n"
                "    :type nums: List[int]\n"
                "    :type target: int\n"
                "    :rtype: List[int]\n"
                "    \"\"\"\n"
                "    # Write your solution here\n"
                "    pass"
            ),
            "test_cases": [
                {"input": [[2, 7, 11, 15], 9],  "output": [0, 1]},
                {"input": [[3, 2, 4], 6],         "output": [1, 2]},
                {"input": [[3, 3], 6],             "output": [0, 1]},
            ]
        },
        {
            "title": "Valid Parentheses",
            "difficulty": "Easy",
            "function_name": "isValid",
            "description": (
                "Given a string `s` containing only '(', ')', '{', '}', '[' and ']', "
                "determine if the input string is valid. "
                "An input string is valid if brackets are closed in the correct order."
            ),
            "examples": [
                {"input": 's = "()"',     "output": "True",  "explanation": "Single matching pair."},
                {"input": 's = \"(]\"', "output": "False", "explanation": "Mismatched brackets."},
            ],
            "constraints": ["1 <= s.length <= 10^4", "s consists of parentheses only."],
            "starter_code": (
                "def isValid(s):\n"
                "    \"\"\"\n"
                "    :type s: str\n"
                "    :rtype: bool\n"
                "    \"\"\"\n"
                "    # Write your solution here\n"
                "    pass"
            ),
            "test_cases": [
                {"input": ["()"],     "output": True},
                {"input": ["()[]{}"], "output": True},
                {"input": ["(]"],     "output": False},
                {"input": ["{[]}"],   "output": True},
            ]
        },
        {
            "title": "Palindrome Number",
            "difficulty": "Easy",
            "function_name": "isPalindrome",
            "description": (
                "Given an integer `x`, return `True` if `x` is a palindrome integer, "
                "and `False` otherwise. An integer is a palindrome when it reads the same "
                "backward as forward."
            ),
            "examples": [
                {"input": "x = 121",  "output": "True",  "explanation": "121 reversed is 121."},
                {"input": "x = -121", "output": "False", "explanation": "Negative numbers are not palindromes."},
            ],
            "constraints": ["-2^31 <= x <= 2^31 - 1"],
            "starter_code": (
                "def isPalindrome(x):\n"
                "    \"\"\"\n"
                "    :type x: int\n"
                "    :rtype: bool\n"
                "    \"\"\"\n"
                "    # Write your solution here\n"
                "    pass"
            ),
            "test_cases": [
                {"input": [121],   "output": True},
                {"input": [-121],  "output": False},
                {"input": [10],    "output": False},
                {"input": [12321], "output": True},
            ]
        },
    ],
    'medium': [
        {
            "title": "Longest Substring Without Repeating Characters",
            "difficulty": "Medium",
            "function_name": "lengthOfLongestSubstring",
            "description": (
                "Given a string `s`, find the length of the longest substring "
                "that contains no repeating characters."
            ),
            "examples": [
                {
                    "input": 's = "abcabcbb"',
                    "output": "3",
                    "explanation": "The answer is 'abc', with length 3."
                }
            ],
            "constraints": [
                "0 <= s.length <= 5 * 10^4",
                "s consists of English letters, digits, symbols, and spaces."
            ],
            "starter_code": (
                "def lengthOfLongestSubstring(s):\n"
                "    \"\"\"\n"
                "    :type s: str\n"
                "    :rtype: int\n"
                "    \"\"\"\n"
                "    # Write your solution here\n"
                "    pass"
            ),
            "test_cases": [
                {"input": ["abcabcbb"], "output": 3},
                {"input": ["bbbbb"],    "output": 1},
                {"input": ["pwwkew"],   "output": 3},
                {"input": [""],         "output": 0},
            ]
        },
        {
            "title": "Maximum Subarray",
            "difficulty": "Medium",
            "function_name": "maxSubArray",
            "description": (
                "Given an integer array `nums`, find the contiguous subarray "
                "with the largest sum and return its sum (Kadane's algorithm)."
            ),
            "examples": [
                {
                    "input": "nums = [-2, 1, -3, 4, -1, 2, 1, -5, 4]",
                    "output": "6",
                    "explanation": "The subarray [4, -1, 2, 1] has the largest sum = 6."
                }
            ],
            "constraints": ["1 <= nums.length <= 10^5", "-10^4 <= nums[i] <= 10^4"],
            "starter_code": (
                "def maxSubArray(nums):\n"
                "    \"\"\"\n"
                "    :type nums: List[int]\n"
                "    :rtype: int\n"
                "    \"\"\"\n"
                "    # Write your solution here\n"
                "    pass"
            ),
            "test_cases": [
                {"input": [[-2, 1, -3, 4, -1, 2, 1, -5, 4]], "output": 6},
                {"input": [[1]],                               "output": 1},
                {"input": [[5, 4, -1, 7, 8]],                 "output": 23},
            ]
        },
        {
            "title": "Group Anagrams",
            "difficulty": "Medium",
            "function_name": "groupAnagrams",
            "description": (
                "Given an array of strings `strs`, group the anagrams together. "
                "Return the answer in any order. "
                "An anagram is a word formed by rearranging the letters of another."
            ),
            "examples": [
                {
                    "input": 'strs = ["eat","tea","tan","ate","nat","bat"]',
                    "output": '[["bat"], ["nat","tan"], ["ate","eat","tea"]]',
                    "explanation": "Words that are anagrams of each other are grouped."
                }
            ],
            "constraints": [
                "1 <= strs.length <= 10^4",
                "0 <= strs[i].length <= 100",
                "strs[i] consists of lowercase English letters."
            ],
            "starter_code": (
                "from typing import List\n\n"
                "def groupAnagrams(strs):\n"
                "    \"\"\"\n"
                "    :type strs: List[str]\n"
                "    :rtype: List[List[str]]\n"
                "    \"\"\"\n"
                "    # Write your solution here\n"
                "    pass"
            ),
            "test_cases": [
                {
                    "input": [["eat", "tea", "tan", "ate", "nat", "bat"]],
                    "output": [["bat"], ["nat", "tan"], ["ate", "eat", "tea"]]
                },
                {"input": [[""]], "output": [[""]]},
                {"input": [["a"]], "output": [["a"]]},
            ]
        },
    ],
    'hard': [
        {
            "title": "Median of Two Sorted Arrays",
            "difficulty": "Hard",
            "function_name": "findMedianSortedArrays",
            "description": (
                "Given two sorted arrays `nums1` and `nums2` of sizes m and n, "
                "return the median of the two sorted arrays. "
                "The overall run time complexity should be O(log(m+n))."
            ),
            "examples": [
                {
                    "input": "nums1 = [1, 3], nums2 = [2]",
                    "output": "2.0",
                    "explanation": "Merged array = [1, 2, 3] → median is 2."
                },
                {
                    "input": "nums1 = [1, 2], nums2 = [3, 4]",
                    "output": "2.5",
                    "explanation": "Merged array = [1, 2, 3, 4] → median is (2+3)/2 = 2.5."
                }
            ],
            "constraints": [
                "nums1.length == m, nums2.length == n",
                "0 <= m, n <= 1000",
                "1 <= m + n <= 2000"
            ],
            "starter_code": (
                "from typing import List\n\n"
                "def findMedianSortedArrays(nums1, nums2):\n"
                "    \"\"\"\n"
                "    :type nums1: List[int]\n"
                "    :type nums2: List[int]\n"
                "    :rtype: float\n"
                "    \"\"\"\n"
                "    # Write your solution here\n"
                "    pass"
            ),
            "test_cases": [
                {"input": [[1, 3], [2]],    "output": 2.0},
                {"input": [[1, 2], [3, 4]], "output": 2.5},
                {"input": [[0, 0], [0, 0]], "output": 0.0},
            ]
        },
        {
            "title": "Trapping Rain Water",
            "difficulty": "Hard",
            "function_name": "trap",
            "description": (
                "Given `n` non-negative integers representing an elevation map where "
                "each bar has width 1, calculate how much water can be trapped after raining."
            ),
            "examples": [
                {
                    "input": "height = [0,1,0,2,1,0,1,3,2,1,2,1]",
                    "output": "6",
                    "explanation": "6 units of water are trapped between the bars."
                }
            ],
            "constraints": [
                "n == height.length",
                "1 <= n <= 2 * 10^4",
                "0 <= height[i] <= 10^5"
            ],
            "starter_code": (
                "from typing import List\n\n"
                "def trap(height):\n"
                "    \"\"\"\n"
                "    :type height: List[int]\n"
                "    :rtype: int\n"
                "    \"\"\"\n"
                "    # Write your solution here\n"
                "    pass"
            ),
            "test_cases": [
                {"input": [[0,1,0,2,1,0,1,3,2,1,2,1]], "output": 6},
                {"input": [[4,2,0,3,2,5]],              "output": 9},
                {"input": [[3,0,2,0,4]],                "output": 7},
            ]
        },
    ]
}


def get_fallback_coding_problem(difficulty='medium'):
    """Return a random pre-built coding problem for the given difficulty."""
    key = difficulty.lower() if difficulty.lower() in _FALLBACK_PROBLEMS else 'medium'
    return random.choice(_FALLBACK_PROBLEMS[key])

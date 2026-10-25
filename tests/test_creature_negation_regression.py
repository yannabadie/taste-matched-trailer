"""Scoped creature-negation regressions: pure synthetic visual text only.

Explicit exclusions are not visible creatures. Affirmative clauses, contrasts
and double negatives remain detectable. No provider/model/recorded output.
"""
import copy
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "taste-matched-trailer"))


def offline(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
        raise AssertionError("Creature regression forbids transport/subprocess/model effects")


sys.addaudithook(offline)
import cultural_launch_director as core


def creature_errors(visual):
    shot = {"visual_prompt": visual, "on_screen_text": "An uncertain feeling.",
            "voiceover": "", "sonic_direction": "", "duration_seconds": 10,
            "aspect_ratio": "16:9", "assets": ["objects", "typography"]}
    brief = {"completeness": "complete", "user_constraints": {
        "duration_seconds": 40, "aspect_ratio": "16:9", "no_visible_monster": True,
        "sound_off": True, "assets": ["objects", "typography"]},
        "shots": [{**copy.deepcopy(shot), "id": f"shot_{n:02d}"} for n in range(1, 5)]}
    return [e for e in core.validate_constraint_fidelity(brief) if "explicit creature conflicts" in e]


class CreatureNegationRegressionTests(unittest.TestCase):
    def test_explicit_exclusion_list_is_not_a_shown_creature(self):
        self.assertEqual(creature_errors("No person, face, hand, silhouette, creature, or reflection."), [])

    def test_scope_contrasts_and_double_negations_keep_affirmative_creatures_visible(self):
        cases = [
            ("Sans créature ni monstre visible ; une porte fermée.", False),
            ("Aucune personne, silhouette, créature ou monstre visible.", False),
            ("No creature. A monster appears beside the door.", True),
            ("No creature, but a monster appears beside the door.", True),
            ("Not a creature but a monster appears.", True),
            ("No creature, except a monster enters.", True),
            ("Pas de créature, mais un monstre entre.", True),
            ("Pas de créature. Une créature apparaît.", True),
            ("Not without a creature.", True),
            ("Not no creature.", True),
            ("Pas sans créature.", True),
            ("Pas aucune créature.", True),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(bool(creature_errors(text)), expected)


    def test_comma_and_clauses_remain_affirmative_while_explicit_negative_joins_stay_negative(self):
        for text, expected in [
            ("No music, and monsters emerge from the dark.", True),
            ("No music, and monsters and creatures emerge from the dark.", True),
            ("No music, and monsters, creatures, and humanoid figures emerge.", True),
            ("Sans musique, et monstres et creatures apparaissent.", True),
            ("No creature, and monsters appear.", True),
            ("Sans musique, et monstres apparaissent.", True),
            ("No creature, nor monsters appear.", False),
            ("Sans creature, ni monstres apparaissent.", False),
            ("No music, and no creature appears.", False),
            ("No person, face, hand, silhouette, creature, or reflection.", False),
            ("No people, hands, faces, and creatures.", False),
        ]:
            with self.subTest(text=text):
                self.assertEqual(bool(creature_errors(text)), expected)
        self.assertTrue(core._visible_person_form("No music, and people stand by the door."))
        self.assertTrue(core._visible_person_form("No music, and people and hands stand by the door."))
        self.assertTrue(core._visible_phenomenon_form("No music, and humanoid figures and spectral shadows appear."))
        self.assertTrue(core._visible_phenomenon_form("No music, and humanoid figures appear."))

if __name__ == "__main__":
    unittest.main(verbosity=2)

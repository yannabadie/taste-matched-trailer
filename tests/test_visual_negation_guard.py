"""Narrow visual-negation regressions. No model, provider or recorded output.

EN/FR nominal lists only; an affirmative clause after a denial stays visible.
These invented strings are not additional creative benchmark cases.
"""
from pathlib import Path
import importlib.util
import sys
import unittest
sys.dont_write_bytecode = True

def offline_only(event, args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise RuntimeError("Visual guard tests forbid network and subprocesses")
sys.addaudithook(offline_only)
source = Path(__file__).resolve().parents[1] / "taste-matched-trailer/cultural_launch_director.py"
spec = importlib.util.spec_from_file_location("visual_guard_candidate", source)
core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)

class VisualNegations(unittest.TestCase):
    def test_explicit_person_nominal_negations_and_lists_en_fr(self):
        for text in [
            "Objects only; no people, hands, faces or figures.",
            "Without any people or hands, a book lies still.",
            "Not a narrator or a human face.",
            "No furniture or people appear.",
            "No human is visible.",
            "No visible human face.",
            "Without the narrator's face.",
            "Sans personne, mains ni visages.",
            "Aucune personne, aucune main ni aucun visage.",
            "Pas de personne ni de main.",
            "Sans le visage du narrateur.",
            "Aucun humain visible.",
            "Pas d'homme ni de femme.",
        ]:
            with self.subTest(text=text): self.assertFalse(core._visible_person_form(text))

    def test_explicit_shape_nominal_negations_and_lists_en_fr(self):
        for text in [
            "No anomaly or figure appears.",
            "No other person, figure or reflection appears.",
            "No silhouettes enter; no spectral outline appears.",
            "Neither a figure nor a humanoid outline appears.",
            "Not a human-shaped shadow.",
            "No furniture, figures or human shadows appear.",
            "Sans anomalie ni forme humaine.",
            "Aucune silhouette ni forme humaine n'apparaît.",
            "Pas de silhouette, contour ou forme humaine.",
        ]:
            with self.subTest(text=text): self.assertFalse(core._visible_phenomenon_form(text))

    def test_positive_people_and_contrasts_still_refused(self):
        for text in [
            "A person stands beside the table.", "The narrator reads a letter.",
            "Hands turn a page.", "Faces fill the frame.", "Une main entre dans le cadre.",
            "No people, but a woman enters the room.",
            "No people, except a narrator beside the desk.",
            "No hands. An actor appears.",
            "No people, a woman stands at the door.",
            "Without people or hands, the narrator's face appears.",
            "Neither a face nor hands, except a man.",
            "Pas de personnage, mais une main entre.",
            "Aucune personne ; un narrateur est visible.",
            "Sans personne, sauf une femme près de la porte.",
            "Not without people.", "Not no people.", "Pas sans personne.", "Pas aucune personne.",
        ]:
            with self.subTest(text=text): self.assertTrue(core._visible_person_form(text))

    def test_positive_shapes_after_denial_and_narrator_do_not_get_plan_wide_exemption(self):
        for text in [
            "A humanoid figure appears behind the desk.",
            "No figures enter. A silhouette stands in the doorway.",
            "Not a figure but a humanoid shadow.",
            "No figure appears, but a humanoid shadow remains.",
            "No anomaly or figure appears. A human shadow is visible.",
            "Sans silhouette, une forme humaine se tient près de la porte.",
            "Pas de forme humaine. Une silhouette se tient dans l'entrée.",
            "Pas de silhouette ni contour humain, mais une figure apparaît.",
            "The narrator's ordinary face is visible while a humanoid figure emerges.",
            "Not without a humanoid figure.", "Pas sans forme humaine.",
        ]:
            with self.subTest(text=text): self.assertTrue(core._visible_phenomenon_form(text))

    def test_ordinary_narrator_and_object_shadow_stay_allowed_without_objects_only(self):
        for text in ["The narrator's ordinary face looks down at a letter.", "An ordinary pencil casts a shadow."]:
            with self.subTest(text=text): self.assertFalse(core._visible_phenomenon_form(text))

    def test_documented_narrow_limit_postverbal_denial_is_not_semantically_understood(self):
        # Deliberately preserve this known conservative false positive. There is
        # no broad clause exemption from the word 'not' that could hide a person.
        self.assertTrue(core._visible_person_form("The narrator is not visible."))

if __name__ == "__main__": unittest.main(verbosity=2)

# Copyright 2019 TerraPower, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Test densityTools."""
# pylint: disable=missing-function-docstring,missing-class-docstring,abstract-method,protected-access,no-member,disallowed-name,invalid-name
import unittest

from armi.utils import densityTools
from armi.nucDirectory import elements, nuclideBases
from armi.materials.uraniumOxide import UO2


class Test_densityTools(unittest.TestCase):
    def test_expandElementalMassFracsToNuclides(self):
        element = elements.bySymbol["N"]
        mass = {"N": 1.0}
        densityTools.expandElementalMassFracsToNuclides(mass, [(element, None)])
        self.assertNotIn("N", mass)
        self.assertIn("N15", mass)
        self.assertIn("N14", mass)
        self.assertAlmostEqual(sum(mass.values()), 1.0)
        self.assertNotIn("N13", mass)  # nothing unnatural.

    def test_expandElementalZeroMassFrac(self):
        """As above, but try with a zero mass frac elemental."""
        elementals = [(elements.bySymbol["N"], None), (elements.bySymbol["O"], None)]
        mass = {"N": 0.0, "O": 1.0}
        densityTools.expandElementalMassFracsToNuclides(mass, elementals)
        self.assertNotIn("N", mass)
        self.assertNotIn("O", mass)
        # Current expectation is for elements with zero mass fraction get expanded and
        # isotopes with zero mass remain in the dictionary.
        self.assertIn("N14", mass)
        self.assertAlmostEqual(sum(mass.values()), 1.0)

    def test_getChemicals(self):

        u235 = nuclideBases.byName["U235"]
        u238 = nuclideBases.byName["U238"]
        o16 = nuclideBases.byName["O16"]

        uo2 = UO2()
        uo2Chemicals = densityTools.getChemicals(uo2.p.massFrac)
        for symbol in ["U", "O"]:
            self.assertIn(symbol, uo2Chemicals.keys())

        self.assertAlmostEqual(
            uo2Chemicals["U"], uo2.p.massFrac["U235"] + uo2.p.massFrac["U238"], 6
        )
        self.assertAlmostEqual(uo2Chemicals["O"], uo2.p.massFrac["O"], 6)

        # ensure getChemicals works if the nuclideBase is the dict key
        massFrac = {u238: 0.87, u235: 0.12, o16: 0.01}
        uo2Chemicals = densityTools.getChemicals(massFrac)
        for symbol in ["U", "O"]:
            self.assertIn(symbol, uo2Chemicals.keys())

        self.assertAlmostEqual(uo2Chemicals["U"], massFrac[u235] + massFrac[u238], 2)
        self.assertAlmostEqual(uo2Chemicals["O"], massFrac[o16], 2)

    def test_expandElement(self):
        """Ensure isotopic subset feature works in expansion."""
        elemental = elements.bySymbol["O"]
        massFrac = 1.0
        subset = [nuclideBases.byName["O16"], nuclideBases.byName["O17"]]
        m1 = densityTools.expandElementalNuclideMassFracs(elemental, massFrac)
        m2 = densityTools.expandElementalNuclideMassFracs(elemental, massFrac, subset)
        self.assertIn("O18", m1)
        self.assertNotIn("O18", m2)
        self.assertAlmostEqual(1.0, sum(m1.values()))
        self.assertAlmostEqual(1.0, sum(m2.values()))
        # expect some small difference due to renormalization
        self.assertNotAlmostEqual(m1["O17"], m2["O17"])
        self.assertAlmostEqual(m1["O17"], m2["O17"], delta=1e-5)

    def test_applyIsotopicsMix(self):
        """Ensure isotopc classes get mixed properly."""
        uo2 = UO2()
        massFracO = uo2.p.massFrac["O"]
        uo2.p.class1_wt_frac = 0.2
        enrichedMassFracs = {"U235": 0.3, "U234": 0.1, "PU239": 0.6}
        fertileMassFracs = {"U238": 0.3, "PU240": 0.7}
        densityTools.applyIsotopicsMix(uo2, enrichedMassFracs, fertileMassFracs)

        self.assertAlmostEqual(
            uo2.p.massFrac["U234"], (1 - massFracO) * 0.2 * 0.1
        )  # HM blended
        self.assertAlmostEqual(
            uo2.p.massFrac["U238"], (1 - massFracO) * 0.8 * 0.3
        )  # HM blended
        self.assertAlmostEqual(uo2.p.massFrac["O"], massFracO)  # non-HM stays unchanged

    def test_getMassFractions(self):
        numDens = {"O17": 0.1512, "PU239": 1.5223, "U234": 0.135}
        massFracs = densityTools.getMassFractions(numDens)

        self.assertAlmostEqual(massFracs["O17"], 0.006456746320668389)
        self.assertAlmostEqual(massFracs["PU239"], 0.9141724414849527)
        self.assertAlmostEqual(massFracs["U234"], 0.07937081219437897)

    def test_calculateNumberDensity(self):
        nDens = densityTools.calculateNumberDensity("U235", 1, 1)
        self.assertAlmostEqual(nDens, 0.0025621344549254283)

        nDens = densityTools.calculateNumberDensity("PU239", 0.00012, 0.001)
        self.assertAlmostEqual(nDens, 0.0003023009578309138)

        nDens = densityTools.calculateNumberDensity("N15", 111, 222)
        self.assertAlmostEqual(nDens, 0.020073659896941428)

    def test_getMassInGrams(self):
        m = densityTools.getMassInGrams("N16", 1.001, None)
        self.assertEqual(m, 0)

        m = densityTools.getMassInGrams("O17", 1.001, 0.00123)
        self.assertAlmostEqual(m, 0.034754813848559635)

        m = densityTools.getMassInGrams("PU239", 1.001, 2.123)
        self.assertAlmostEqual(m, 843.5790671316283)

    def test_normalizeNuclideList(self):
        nList = {"PU239": 23.2342, "U234": 0.001234, "U235": 34.152}
        norm = densityTools.normalizeNuclideList(nList)

        self.assertAlmostEqual(norm["PU239"], 0.40486563661306063)
        self.assertAlmostEqual(norm["U234"], 2.1502965265880334e-05)
        self.assertAlmostEqual(norm["U235"], 0.5951128604216736)


if __name__ == "__main__":
    unittest.main()

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
"""
Tests some capabilities of the fuel handling machine.

This test is high enough level that it requires input files to be present. The ones to use
are called armiRun.yaml which is located in armi.tests
"""
# pylint: disable=missing-function-docstring,missing-class-docstring,protected-access,invalid-name,no-self-use,no-method-argument,import-outside-toplevel
import collections
import copy
import unittest

import numpy as np

from armi.physics.fuelCycle import fuelHandlers, settings
from armi.reactor import assemblies, blocks, components, grids
from armi.reactor.flags import Flags
from armi.reactor.tests import test_reactors
from armi.settings import caseSettings
from armi.tests import ArmiTestHelper, TEST_ROOT
from armi.utils import directoryChangers


class FuelHandlerTestHelper(ArmiTestHelper):
    @classmethod
    def setUpClass(cls):
        # prepare the input files. This is important so the unit tests run from wherever
        # they need to run from.
        cls.directoryChanger = directoryChangers.DirectoryChanger(
            TEST_ROOT, dumpOnException=False
        )
        cls.directoryChanger.open()

    @classmethod
    def tearDownClass(cls):
        cls.directoryChanger.close()

    def setUp(self):
        r"""
        Build a dummy reactor without using input files. There are some igniters and feeds
        but none of these have any number densities.
        """
        self.o, self.r = test_reactors.loadTestReactor(
            self.directoryChanger.destination,
            customSettings={"nCycles": 3, "trackAssems": True},
        )

        blockList = self.r.core.getBlocks()
        for bi, b in enumerate(blockList):
            b.p.flux = 5e10
            if b.isFuel():
                b.p.percentBu = 30.0 * bi / len(blockList)
        self.nfeed = len(self.r.core.getAssemblies(Flags.FEED))
        self.nigniter = len(self.r.core.getAssemblies(Flags.IGNITER))
        self.nSfp = len(self.r.core.sfp)

        # generate a reactor with assemblies
        # generate components with materials
        nPins = 271

        fuelDims = {"Tinput": 273.0, "Thot": 273.0, "od": 1.0, "id": 0.0, "mult": nPins}
        fuel = components.Circle("fuel", "UZr", **fuelDims)

        cladDims = {"Tinput": 273.0, "Thot": 273.0, "od": 1.1, "id": 1.0, "mult": nPins}
        clad = components.Circle("clad", "HT9", **cladDims)

        interDims = {
            "Tinput": 273.0,
            "Thot": 273.0,
            "op": 16.8,
            "ip": 16.0,
            "mult": 1.0,
        }
        interSodium = components.Hexagon("interCoolant", "Sodium", **interDims)

        # generate a block
        self.block = blocks.HexBlock("TestHexBlock")
        self.block.setType("fuel")
        self.block.setHeight(10.0)
        self.block.add(fuel)
        self.block.add(clad)
        self.block.add(interSodium)

        # generate an assembly
        self.assembly = assemblies.HexAssembly("TestAssemblyType")
        self.assembly.spatialGrid = grids.axialUnitGrid(1)
        for _ in range(1):
            self.assembly.add(copy.deepcopy(self.block))

        # copy the assembly to make a list of assemblies and have a reference assembly
        self.aList = []
        for _ in range(6):
            self.aList.append(copy.deepcopy(self.assembly))

        self.refAssembly = copy.deepcopy(self.assembly)
        self.directoryChanger.open()

    def tearDown(self):
        # clean up the test
        self.block = None
        self.assembly = None
        self.aList = None
        self.refAssembly = None
        self.r = None
        self.o = None

        self.directoryChanger.close()


class TestFuelHandler(FuelHandlerTestHelper):
    def test_findHighBu(self):
        loc = self.r.core.spatialGrid.getLocatorFromRingAndPos(5, 4)
        a = self.r.core.childrenByLocator[loc]
        # set burnup way over 1.0, which is otherwise the highest bu in the core
        a[0].p.percentBu = 50

        fh = fuelHandlers.FuelHandler(self.o)
        a1 = fh.findAssembly(
            param="percentBu", compareTo=100, blockLevelMax=True, typeSpec=None
        )
        self.assertIs(a, a1)

    def test_width(self):
        """Tests the width capability of findAssembly."""
        fh = fuelHandlers.FuelHandler(self.o)
        assemsByRing = collections.defaultdict(list)
        for a in self.r.core.getAssemblies():
            assemsByRing[a.spatialLocator.getRingPos()[0]].append(a)

        # instantiate reactor power. more power in more outer rings
        for ring, power in zip(range(1, 8), range(10, 80, 10)):
            aList = assemsByRing[ring]
            for a in aList:
                for b in a:
                    b.p.power = power

        paramName = "power"
        # 1 ring outer and inner from ring 3
        a = fh.findAssembly(
            targetRing=3,
            width=(1, 0),
            param=paramName,
            blockLevelMax=True,
            compareTo=100,
        )
        ring = a.spatialLocator.getRingPos()[0]
        self.assertEqual(
            ring,
            4,
            "The highest power ring returned is {0}. It should be {1}".format(ring, 4),
        )
        a = fh.findAssembly(
            targetRing=3, width=(1, 0), param=paramName, blockLevelMax=True, compareTo=0
        )
        ring = a.spatialLocator.getRingPos()[0]
        self.assertEqual(
            ring,
            2,
            "The lowest power ring returned is {0}. It should be {1}".format(ring, 2),
        )

        # 2 rings outer from ring 3
        a = fh.findAssembly(
            targetRing=3,
            width=(2, 1),
            param=paramName,
            blockLevelMax=True,
            compareTo=100,
        )
        ring = a.spatialLocator.getRingPos()[0]
        self.assertEqual(
            ring,
            5,
            "The highest power ring returned is {0}. It should be {1}".format(ring, 5),
        )
        a = fh.findAssembly(
            targetRing=3, width=(2, 1), param=paramName, blockLevelMax=True, compareTo=0
        )
        ring = a.spatialLocator.getRingPos()[0]
        self.assertEqual(
            ring,
            3,
            "The lowest power ring returned is {0}. It should be {1}".format(ring, 3),
        )

        # 2 rings inner from ring 3
        a = fh.findAssembly(
            targetRing=3,
            width=(2, -1),
            param=paramName,
            blockLevelMax=True,
            compareTo=100,
        )
        ring = a.spatialLocator.getRingPos()[0]
        self.assertEqual(
            ring,
            3,
            "The highest power ring returned is {0}. It should be {1}".format(ring, 3),
        )
        a = fh.findAssembly(
            targetRing=3,
            width=(2, -1),
            param=paramName,
            blockLevelMax=True,
            compareTo=0,
        )
        ring = a.spatialLocator.getRingPos()[0]
        self.assertEqual(
            ring,
            1,
            "The lowest power ring returned is {0}. It should be {1}".format(ring, 1),
        )

    def test_findMany(self):
        """Tests the findMany and type aspects of the fuel handler"""
        fh = fuelHandlers.FuelHandler(self.o)

        igniters = fh.findAssembly(typeSpec=Flags.IGNITER | Flags.FUEL, findMany=True)
        feeds = fh.findAssembly(typeSpec=Flags.FEED | Flags.FUEL, findMany=True)
        fewFeeds = fh.findAssembly(
            typeSpec=Flags.FEED | Flags.FUEL, findMany=True, maxNumAssems=4
        )

        self.assertEqual(
            len(igniters),
            self.nigniter,
            "Found {0} igniters. Should have found {1}".format(
                len(igniters), self.nigniter
            ),
        )
        self.assertEqual(
            len(feeds),
            self.nfeed,
            "Found {0} feeds. Should have found {1}".format(len(igniters), self.nfeed),
        )
        self.assertEqual(
            len(fewFeeds),
            4,
            "Reduced findMany returned {0} assemblies instead of {1}"
            "".format(len(fewFeeds), 4),
        )

    def test_findInSFP(self):
        """Tests ability to pull from the spent fuel pool"""
        fh = fuelHandlers.FuelHandler(self.o)
        spent = fh.findAssembly(
            findMany=True,
            findFromSfp=True,
            param="percentBu",
            compareTo=100,
            blockLevelMax=True,
        )
        self.assertEqual(
            len(spent),
            self.nSfp,
            "Found {0} assems in SFP. Should have found {1}".format(
                len(spent), self.nSfp
            ),
        )
        burnups = [a.getMaxParam("percentBu") for a in spent]
        bu = spent[0].getMaxParam("percentBu")
        self.assertEqual(
            bu,
            max(burnups),
            "First assembly does not have the "
            "highest burnup ({0}). It has ({1})".format(max(burnups), bu),
        )

    def test_findByCoords(self):
        fh = fuelHandlers.FuelHandler(self.o)
        assem = fh.findAssembly(coords=(0, 0))
        self.assertIs(assem, self.o.r.core[0])

    def test_findWithMinMax(self):
        """Test the complex min/max comparators."""
        fh = fuelHandlers.FuelHandler(self.o)
        assem = fh.findAssembly(
            param="percentBu",
            compareTo=100,
            blockLevelMax=True,
            minParam="percentBu",
            minVal=("percentBu", 0.1),
            maxParam="percentBu",
            maxVal=20.0,
        )
        # the burnup should be the maximum bu within
        # up to a burnup of 20%, which by the simple
        # dummy data layout should be the 2/3rd block in the blocklist
        bs = self.r.core.getBlocks(Flags.FUEL)
        lastB = None
        for b in bs:
            if b.p.percentBu > 20:
                break
            lastB = b
        expected = lastB.parent
        self.assertIs(assem, expected)

        # test the impossible: an block with burnup less than
        # 110% of its own burnup
        assem = fh.findAssembly(
            param="percentBu",
            compareTo=100,
            blockLevelMax=True,
            minParam="percentBu",
            minVal=("percentBu", 1.1),
        )
        self.assertIsNone(assem)

    def runShuffling(self, fh):
        """Shuffle fuel and write out a SHUFFLES.txt file."""
        fh.attachReactor(self.o, self.r)

        # so we don't overwrite the version-controlled armiRun-SHUFFLES.txt
        self.o.cs.caseTitle = "armiRun2"
        fh.interactBOL()

        for cycle in range(3):
            self.r.p.cycle = cycle
            fh.cycle = cycle
            fh.manageFuel(cycle)
            for a in self.r.core.sfp.getChildren():
                self.assertEqual(a.getLocation(), "SFP")
        fh.interactEOL()

    def test_repeatShuffles(self):
        r"""
        Builds a dummy core. Does some shuffles. Repeats the shuffles. Checks that it was a perfect repeat.

        Checks some other things in the meantime

        See Also
        --------
        runShuffling : creates the shuffling file to be read in.
        """
        # check labels before shuffling:
        for a in self.r.core.sfp.getChildren():
            self.assertEqual(a.getLocation(), "SFP")

        # do some shuffles.
        fh = self.r.o.getInterface("fuelHandler")
        self.runShuffling(fh)  # changes caseTitle

        # make sure the generated shuffles file matches the tracked one.
        # This will need to be updated if/when more assemblies are added to the test reactor
        # but must be done carefully. Do not blindly rebaseline this file.
        self.compareFilesLineByLine("armiRun-SHUFFLES.txt", "armiRun2-SHUFFLES.txt")

        # store locations of each assembly
        firstPassResults = {}
        for a in self.r.core.getAssemblies():
            firstPassResults[a.getLocation()] = a.getName()
            self.assertNotIn(a.getLocation(), ["SFP", "LoadQueue", "ExCore"])

        # reset core to BOL state
        # reset assembly counter to get the same assem nums.
        self.setUp()

        newSettings = {"plotShuffleArrows": True}
        # now repeat shuffles
        newSettings["explicitRepeatShuffles"] = "armiRun-SHUFFLES.txt"
        self.o.cs = self.o.cs.modified(newSettings=newSettings)

        fh = self.r.o.getInterface("fuelHandler")

        self.runShuffling(fh)

        # make sure the shuffle was repeated perfectly.
        for a in self.r.core.getAssemblies():
            self.assertEqual(a.getName(), firstPassResults[a.getLocation()])
        for a in self.r.core.sfp.getChildren():
            self.assertEqual(a.getLocation(), "SFP")

    def test_readMoves(self):
        """
        Depends on the shuffleLogic created by repeatShuffles

        See Also
        --------
        runShuffling : creates the shuffling file to be read in.
        """
        numblocks = len(self.r.core.getFirstAssembly())
        fh = fuelHandlers.FuelHandler(self.o)
        moves = fh.readMoves("armiRun-SHUFFLES.txt")
        self.assertEqual(len(moves), 3)
        firstMove = moves[1][0]
        self.assertEqual(firstMove[0], "002-001")
        self.assertEqual(firstMove[1], "SFP")
        self.assertEqual(len(firstMove[2]), numblocks)
        self.assertEqual(firstMove[3], "igniter fuel")
        self.assertEqual(firstMove[4], None)

        # check the move that came back out of the SFP
        sfpMove = moves[2][-2]
        self.assertEqual(sfpMove[0], "SFP")
        self.assertEqual(sfpMove[1], "005-003")
        self.assertEqual(sfpMove[4], "A0085")  # name of assem in SFP

    def test_processMoveList(self):
        fh = fuelHandlers.FuelHandler(self.o)
        moves = fh.readMoves("armiRun-SHUFFLES.txt")
        (
            loadChains,
            loopChains,
            _,
            _,
            loadNames,
            _,
        ) = fh.processMoveList(moves[2])
        self.assertIn("A0085", loadNames)
        self.assertIn(None, loadNames)
        self.assertNotIn("SFP", loadChains)
        self.assertNotIn("LoadQueue", loadChains)
        self.assertFalse(loopChains)

    def test_getFactorList(self):
        fh = fuelHandlers.FuelHandler(self.o)
        factors, _ = fh.getFactorList(0)
        self.assertIn("eqShuffles", factors)

    def test_linPowByPin(self):
        _fh = fuelHandlers.FuelHandler(self.o)
        _hist = self.o.getInterface("history")
        newSettings = {"assemblyRotationStationary": True}
        self.o.cs = self.o.cs.modified(newSettings=newSettings)
        assem = self.o.r.core.getFirstAssembly(Flags.FUEL)
        b = assem.getBlocks(Flags.FUEL)[0]

        b.p.linPowByPin = [1, 2, 3]
        self.assertEqual(type(b.p.linPowByPin), np.ndarray)

        b.p.linPowByPin = np.array([1, 2, 3])
        self.assertEqual(type(b.p.linPowByPin), np.ndarray)

    def test_linPowByPinNeutron(self):
        _fh = fuelHandlers.FuelHandler(self.o)
        _hist = self.o.getInterface("history")
        newSettings = {"assemblyRotationStationary": True}
        self.o.cs = self.o.cs.modified(newSettings=newSettings)
        assem = self.o.r.core.getFirstAssembly(Flags.FUEL)
        b = assem.getBlocks(Flags.FUEL)[0]

        b.p.linPowByPinNeutron = [1, 2, 3]
        self.assertEqual(type(b.p.linPowByPinNeutron), np.ndarray)

        b.p.linPowByPinNeutron = np.array([1, 2, 3])
        self.assertEqual(type(b.p.linPowByPinNeutron), np.ndarray)

    def test_linPowByPinGamma(self):
        _fh = fuelHandlers.FuelHandler(self.o)
        _hist = self.o.getInterface("history")
        newSettings = {"assemblyRotationStationary": True}
        self.o.cs = self.o.cs.modified(newSettings=newSettings)
        assem = self.o.r.core.getFirstAssembly(Flags.FUEL)
        b = assem.getBlocks(Flags.FUEL)[0]

        b.p.linPowByPinGamma = [1, 2, 3]
        self.assertEqual(type(b.p.linPowByPinGamma), np.ndarray)

        b.p.linPowByPinGamma = np.array([1, 2, 3])
        self.assertEqual(type(b.p.linPowByPinGamma), np.ndarray)

    def test_getRingAssemblies(self):
        fh = fuelHandlers.FuelHandler(self.o)

        # simple
        schedule = [[2], [1]]
        assemblies = fuelHandlers.translationFunctions.getRingAssemblies(fh, schedule)
        self.assertEqual(
            [[assy.getLocation() for assy in assyList] for assyList in assemblies],
            [
                [
                    "002-001",
                    "002-002",
                ],
                ["001-001"],
            ],
        )

        # circular ring
        schedule = [[2], [1]]
        assemblies = fuelHandlers.translationFunctions.getRingAssemblies(
            fh, schedule, circular=True
        )
        self.assertEqual(
            [[assy.getLocation() for assy in assyList] for assyList in assemblies],
            [
                ["004-018", "003-001", "004-002", "004-003", "003-003", "004-005"],
                ["001-001", "003-012", "002-001", "003-002", "002-002"],
            ],
        )

        # distance smart sorting
        fh.cs["circularRingOrder"] = "distanceSmart"
        schedule = [[3], [2], [1]]
        assemblies = fuelHandlers.translationFunctions.getRingAssemblies(fh, schedule)
        self.assertEqual(
            [[assy.getLocation() for assy in assyList] for assyList in assemblies],
            [
                ["003-012", "003-002", "003-001", "003-003"],
                ["002-001", "002-002"],
                ["001-001"],
            ],
        )

        # default to distance smart sorting
        fh.cs["circularRingOrder"] = None
        schedule = [[3], [2], [1]]
        assemblies = fuelHandlers.translationFunctions.getRingAssemblies(fh, schedule)
        self.assertEqual(
            [[assy.getLocation() for assy in assyList] for assyList in assemblies],
            [
                ["003-012", "003-002", "003-001", "003-003"],
                ["002-001", "002-002"],
                ["001-001"],
            ],
        )

    def test_getBatchZoneAssembliesFromLocation(self):
        import numpy

        fh = fuelHandlers.FuelHandler(self.o)
        assemblies = (
            fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                fh,
                [
                    [
                        "002-001",
                        "002-002",
                    ],
                    ["001-001"],
                ],
            )
        )
        self.assertEqual(
            [[assy.getLocation() for assy in assyList] for assyList in assemblies],
            [
                [
                    "002-001",
                    "002-002",
                ],
                ["001-001"],
            ],
        )

        # test invalid assembly locations
        with self.assertRaises(RuntimeError):
            invalidAssembly = (
                fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                    fh, [["001-002"]]
                )
            )
        with self.assertRaises(RuntimeError):
            invalidAssembly = (
                fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                    fh, [["002-007"]]
                )
            )
        with self.assertRaises(RuntimeError):
            invalidAssembly = (
                fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                    fh, [["{:03d}-001".format(fh.r.core.getNumRings() + 1)]]
                )
            )

        # test new assembly
        newAssembly = (
            fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                fh, [["new: {}".format(fh.r.core.refAssem.getType())]]
            )
        )
        self.assertEqual(newAssembly[0][0].getType(), fh.r.core.refAssem.getType())
        self.assertEqual(len(newAssembly[0][0]), len(fh.r.core.refAssem))
        # test new assembly with changed enrichment
        newAssembly = (
            fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                fh, [["new: {}; enrichment: 14.5".format(fh.r.core.refAssem.getType())]]
            )
        )
        self.assertEqual(newAssembly[0][0].getType(), fh.r.core.refAssem.getType())
        for block in newAssembly[0][0].getChildrenWithFlags(Flags.FUEL):
            self.assertAlmostEqual(block.p.enrichmentBOL, 14.5, 13)
        # test new assembly with invalid enrichment change
        with self.assertRaises(RuntimeError):
            invalidAssembly = (
                fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                    fh,
                    [["new: {}; enrichment: 5,5".format(fh.r.core.refAssem.getType())]],
                )
            )
        # test invalid new assembly
        with self.assertRaises(RuntimeError):
            invalidAssembly = (
                fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                    fh, [["new: invalidType"]]
                )
            )

        # test sfp assembly
        sfpAssembly = (
            fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                fh, [["sfp: {}".format(fh.r.core.sfp.getChildren()[0].getName())]]
            )
        )
        # test invalid sfp assembly
        with self.assertRaises(RuntimeError):
            invalidAssembly = (
                fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                    fh, [["sfp: invalidAssyName"]]
                )
            )

        # test invalid assembly setting
        with self.assertRaises((NotImplementedError, RuntimeError)):
            invalidAssembly = (
                fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                    fh, [["invalid: 1"]]
                )
            )

        # test sort function
        def _sortTestFun(assembly):
            origin = numpy.array([0.0, 0.0, 0.0])
            p = numpy.array(assembly.spatialLocator.getLocalCoordinates())
            return round(((p - origin) ** 2).sum(), 5)

        assemblies = (
            fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                fh,
                [
                    [
                        "003-001",
                        "003-002",
                    ],
                    ["001-001"],
                ],
                sortFun=_sortTestFun,
            )
        )
        self.assertEqual(
            [[assy.getLocation() for assy in assyList] for assyList in assemblies],
            [
                [
                    "003-002",
                    "003-001",
                ],
                ["001-001"],
            ],
        )

        # test invalid sort function
        with self.assertRaises(RuntimeError):
            assemblies = (
                fuelHandlers.translationFunctions.getBatchZoneAssembliesFromLocation(
                    fh,
                    [
                        [
                            "003-001",
                            "003-002",
                        ],
                        ["001-001"],
                    ],
                    sortFun="a",
                )
            )

    def test_getCascadesFromLocations(self):
        fh = fuelHandlers.FuelHandler(self.o)
        locations = [
            [
                "002-001",
                "002-002",
            ],
            ["001-001"],
        ]
        assemblies = fuelHandlers.translationFunctions.getCascadesFromLocations(
            fh, locations
        )
        self.assertEqual(
            [[assy.getLocation() for assy in assyList] for assyList in assemblies],
            locations,
        )

    def test_buildBatchCascades(self):
        fh = fuelHandlers.FuelHandler(self.o)
        # converging 2 jumps
        schedule = fuelHandlers.translationFunctions.buildRingSchedule(
            self, 1, 3, diverging=False
        )
        assemblies = fuelHandlers.translationFunctions.getRingAssemblies(fh, schedule)
        batchCascade = fuelHandlers.translationFunctions.buildBatchCascades(assemblies)
        self.assertEqual(
            batchCascade,
            fuelHandlers.translationFunctions.getCascadesFromLocations(
                fh,
                [
                    ["003-003"],
                    ["002-001", "003-012"],
                    ["002-002", "003-002"],
                    ["001-001", "003-001"],
                ],
            ),
        )

        # diverging 1 jump
        schedule = fuelHandlers.translationFunctions.buildRingSchedule(
            self, 1, 2, diverging=True
        )
        assemblies = fuelHandlers.translationFunctions.getRingAssemblies(fh, schedule)
        batchCascade = fuelHandlers.translationFunctions.buildBatchCascades(assemblies)
        self.assertEqual(
            batchCascade,
            fuelHandlers.translationFunctions.getCascadesFromLocations(
                fh, [["002-002", "002-001", "001-001"]]
            ),
        )

        # diverging 2 jumps
        schedule = fuelHandlers.translationFunctions.buildRingSchedule(
            self, 1, 3, diverging=True
        )
        assemblies = fuelHandlers.translationFunctions.getRingAssemblies(fh, schedule)
        batchCascade = fuelHandlers.translationFunctions.buildBatchCascades(assemblies)
        self.assertEqual(
            batchCascade,
            fuelHandlers.translationFunctions.getCascadesFromLocations(
                fh,
                [
                    [
                        "003-003",
                        "003-001",
                        "003-002",
                        "003-0012",
                        "002-002",
                        "002-001",
                        "001-001",
                    ]
                ],
            ),
        )

        # new fuel
        schedule = fuelHandlers.translationFunctions.buildRingSchedule(
            self,
            1,
            2,
            diverging=False,
        )
        assemblies = fuelHandlers.translationFunctions.getRingAssemblies(fh, schedule)
        batchCascade = fuelHandlers.translationFunctions.buildBatchCascades(
            assemblies, newFuelName=fh.r.core.refAssem.getType()
        )
        self.assertEqual(
            [[assy.getLocation() for assy in assyList] for assyList in batchCascade],
            [["002-002", "LoadQueue"], ["001-001", "002-001", "LoadQueue"]],
        )

        # invalid new fuel
        schedule = fuelHandlers.translationFunctions.buildRingSchedule(
            self,
            1,
            2,
            diverging=False,
        )
        assemblies = fuelHandlers.translationFunctions.getRingAssemblies(fh, schedule)
        with self.assertRaises(ValueError):
            batchCascade = fuelHandlers.translationFunctions.buildBatchCascades(
                assemblies, newFuelName="invalidType"
            )

    def test_changeBlockLevelEnrichment(self):
        fh = fuelHandlers.FuelHandler(self.o)
        assy = self.r.core.getAssemblies(Flags.FEED)[0]

        # Test single enrichment
        newEnrich = 0.16
        fuelHandlers.translationFunctions.changeBlockLevelEnrichment(assy, newEnrich)
        for block in assy.getBlocks(Flags.FUEL):
            self.assertAlmostEqual(block.getFissileMassEnrich(), 0.16, delta=1e-6)

        # Test enrichment list
        newEnrich = [0.12, 0.14, 0.16]
        fuelHandlers.translationFunctions.changeBlockLevelEnrichment(assy, newEnrich)
        for index, block in enumerate(assy.getBlocks(Flags.FUEL)):
            self.assertAlmostEqual(
                block.getFissileMassEnrich(), newEnrich[index], delta=1e-6
            )

        # Test invalid enrichment list length and invalid enrichment value
        newEnrich = [0.12, 0.14, 0.16, 0.15]
        with self.assertRaises(RuntimeError):
            fuelHandlers.translationFunctions.changeBlockLevelEnrichment(
                assy, newEnrich
            )
        newEnrich = "a"
        with self.assertRaises(RuntimeError):
            fuelHandlers.translationFunctions.changeBlockLevelEnrichment(
                assy, newEnrich
            )

    def test_transferStationaryBlocks(self):
        """
        Test the _transferStationaryBlocks method .
        """
        # grab stationary block flags
        sBFList = self.r.core.stationaryBlockFlagsList

        # grab the assemblies
        assems = self.r.core.getAssemblies(Flags.FUEL)

        # grab two arbitrary assemblies
        a1 = assems[1]
        a2 = assems[2]

        # grab the stationary blocks pre swap
        a1PreSwapStationaryBlocks = [
            [block.getName(), block.spatialLocator.k]
            for block in a1
            if any(block.hasFlags(sbf) for sbf in sBFList)
        ]

        a2PreSwapStationaryBlocks = [
            [block.getName(), block.spatialLocator.k]
            for block in a2
            if any(block.hasFlags(sbf) for sbf in sBFList)
        ]

        # swap the stationary blocks
        fh = fuelHandlers.FuelHandler(self.o)
        fh._transferStationaryBlocks(a1, a2)

        # grab the stationary blocks post swap
        a1PostSwapStationaryBlocks = [
            [block.getName(), block.spatialLocator.k]
            for block in a1
            if any(block.hasFlags(sbf) for sbf in sBFList)
        ]

        a2PostSwapStationaryBlocks = [
            [block.getName(), block.spatialLocator.k]
            for block in a2
            if any(block.hasFlags(sbf) for sbf in sBFList)
        ]

        # validate the stationary blocks have swapped locations and are aligned
        self.assertEqual(a1PostSwapStationaryBlocks, a2PreSwapStationaryBlocks)
        self.assertEqual(a2PostSwapStationaryBlocks, a1PreSwapStationaryBlocks)

    def test_transferIncompatibleStationaryBlocks(self):
        """
        Test the _transferStationaryBlocks method
        for the case where the input assemblies have
        different numbers as well as unaligned locations of stationary blocks.
        """
        # grab stationary block flags
        sBFList = self.r.core.stationaryBlockFlagsList

        # grab the assemblies
        assems = self.r.core.getAssemblies(Flags.FUEL)

        # grab two arbitrary assemblies
        a1 = assems[1]
        a2 = assems[2]

        # change a block in assembly 1 to be flagged as a stationary block
        for block in a1:
            if not any(block.hasFlags(sbf) for sbf in sBFList):
                a1[block.spatialLocator.k].setType(
                    a1[block.spatialLocator.k].p.type, sBFList[0]
                )
                self.assertTrue(any(block.hasFlags(sbf) for sbf in sBFList))
                break

        # try to swap stationary blocks between assembly 1 and 2
        fh = fuelHandlers.FuelHandler(self.o)
        with self.assertRaises(ValueError):
            fh._transferStationaryBlocks(a1, a2)

        # re-initialize assemblies
        self.setUp()
        assems = self.r.core.getAssemblies(Flags.FUEL)
        a1 = assems[1]
        a2 = assems[2]

        # move location of a stationary flag in assembly 1
        for block in a1:
            if any(block.hasFlags(sbf) for sbf in sBFList):
                # change flag of first identified stationary block to fuel
                a1[block.spatialLocator.k].setType(
                    a1[block.spatialLocator.k].p.type, Flags.FUEL
                )
                self.assertTrue(a1[block.spatialLocator.k].hasFlags(Flags.FUEL))
                # change next or previous block flag to stationary flag
                try:
                    a1[block.spatialLocator.k + 1].setType(
                        a1[block.spatialLocator.k + 1].p.type, sBFList[0]
                    )
                    self.assertTrue(
                        any(
                            a1[block.spatialLocator.k + 1].hasFlags(sbf)
                            for sbf in sBFList
                        )
                    )
                except:
                    a1[block.spatialLocator.k - 1].setType(
                        a1[block.spatialLocator.k - 1].p.type, sBFList[0]
                    )
                    self.assertTrue(
                        any(
                            a1[block.spatialLocator.k - 1].hasFlags(sbf)
                            for sbf in sBFList
                        )
                    )
                break

        # try to swap stationary blocks between assembly 1 and 2
        with self.assertRaises(ValueError):
            fh._transferStationaryBlocks(a1, a2)

    def test_dischargeSwap(self):
        """
        Test the dischargeSwap method.
        """
        # grab stationary block flags
        sBFList = self.r.core.stationaryBlockFlagsList

        # grab an arbitrary fuel assembly from the core and from the SFP
        a1 = self.r.core.getAssemblies(Flags.FUEL)[0]
        a2 = self.r.core.sfp.getChildren(Flags.FUEL)[0]

        # grab the stationary blocks pre swap
        a1PreSwapStationaryBlocks = [
            [block.getName(), block.spatialLocator.k]
            for block in a1
            if any(block.hasFlags(sbf) for sbf in sBFList)
        ]

        a2PreSwapStationaryBlocks = [
            [block.getName(), block.spatialLocator.k]
            for block in a2
            if any(block.hasFlags(sbf) for sbf in sBFList)
        ]

        # test discharging assembly 1 and replacing with assembly 2
        fh = fuelHandlers.FuelHandler(self.o)
        fh.dischargeSwap(a2, a1)
        self.assertTrue(a1.getLocation() in a1.NOT_IN_CORE)
        self.assertTrue(a2.getLocation() not in a2.NOT_IN_CORE)

        # grab the stationary blocks post swap
        a1PostSwapStationaryBlocks = [
            [block.getName(), block.spatialLocator.k]
            for block in a1
            if any(block.hasFlags(sbf) for sbf in sBFList)
        ]

        a2PostSwapStationaryBlocks = [
            [block.getName(), block.spatialLocator.k]
            for block in a2
            if any(block.hasFlags(sbf) for sbf in sBFList)
        ]

        # validate the stationary blocks have swapped locations correctly and are aligned
        self.assertEqual(a1PostSwapStationaryBlocks, a2PreSwapStationaryBlocks)
        self.assertEqual(a2PostSwapStationaryBlocks, a1PreSwapStationaryBlocks)

    def test_dischargeSwapIncompatibleStationaryBlocks(self):
        """
        Test the _transferStationaryBlocks method
        for the case where the input assemblies have
        different numbers as well as unaligned locations of stationary blocks.
        """
        # grab stationary block flags
        sBFList = self.r.core.stationaryBlockFlagsList

        # grab an arbitrary fuel assembly from the core and from the SFP
        a1 = self.r.core.getAssemblies(Flags.FUEL)[0]
        a2 = self.r.core.sfp.getChildren(Flags.FUEL)[0]

        # change a block in assembly 1 to be flagged as a stationary block
        for block in a1:
            if not any(block.hasFlags(sbf) for sbf in sBFList):
                a1[block.spatialLocator.k].setType(
                    a1[block.spatialLocator.k].p.type, sBFList[0]
                )
                self.assertTrue(any(block.hasFlags(sbf) for sbf in sBFList))
                break

        # try to discharge assembly 1 and replace with assembly 2
        fh = fuelHandlers.FuelHandler(self.o)
        with self.assertRaises(ValueError):
            fh.dischargeSwap(a2, a1)

        # re-initialize assemblies
        self.setUp()
        a1 = self.r.core.getAssemblies(Flags.FUEL)[0]
        a2 = self.r.core.sfp.getChildren(Flags.FUEL)[0]

        # move location of a stationary flag in assembly 1
        for block in a1:
            if any(block.hasFlags(sbf) for sbf in sBFList):
                # change flag of first identified stationary block to fuel
                a1[block.spatialLocator.k].setType(
                    a1[block.spatialLocator.k].p.type, Flags.FUEL
                )
                self.assertTrue(a1[block.spatialLocator.k].hasFlags(Flags.FUEL))
                # change next or previous block flag to stationary flag
                try:
                    a1[block.spatialLocator.k + 1].setType(
                        a1[block.spatialLocator.k + 1].p.type, sBFList[0]
                    )
                    self.assertTrue(
                        any(
                            a1[block.spatialLocator.k + 1].hasFlags(sbf)
                            for sbf in sBFList
                        )
                    )
                except:
                    a1[block.spatialLocator.k - 1].setType(
                        a1[block.spatialLocator.k - 1].p.type, sBFList[0]
                    )
                    self.assertTrue(
                        any(
                            a1[block.spatialLocator.k - 1].hasFlags(sbf)
                            for sbf in sBFList
                        )
                    )
                break

        # try to discharge assembly 1 and replace with assembly 2
        with self.assertRaises(ValueError):
            fh.dischargeSwap(a2, a1)

    def test_validateAssemblySwap(self):
        """
        Test the _validateAssemblySwap method.
        """

        # grab the assemblies
        assems = self.r.core.getAssemblies(Flags.FUEL)

        # grab two arbitrary assemblies
        a1 = assems[1]
        a2 = assems[2]

        # swap assemblies
        fh = fuelHandlers.FuelHandler(self)
        oldA1Location = a1.spatialLocator
        oldA2Location = a2.spatialLocator
        a1StationaryBlocks, a2StationaryBlocks = fh._transferStationaryBlocks(a1, a2)
        a1.moveTo(oldA2Location)
        self.assertTrue(a1.spatialLocator == oldA2Location)
        a2.moveTo(oldA1Location)
        self.assertTrue(a2.spatialLocator == oldA1Location)

        # swap the stationary blocks back
        fh._transferStationaryBlocks(a1, a2)

        with self.assertRaises(ValueError):
            fh._validateAssemblySwap(
                a1StationaryBlocks, oldA1Location, a2StationaryBlocks, oldA2Location
            )

    def test_validateLocations(self):
        """
        Test the validateLocations method.
        """
        # grab the assemblies
        assems = self.r.core.getAssemblies(Flags.FUEL)

        # grab two arbitrary assemblies
        a1 = assems[1]
        a2 = assems[2]

        # move assembly 1 to assembly 2 location
        a1.moveTo(a2.spatialLocator)
        self.assertTrue(a1.spatialLocator == a2.spatialLocator)

        #
        fh = self.r.o.getInterface("fuelHandler")
        with self.assertRaises(ValueError):
            fh.validateLocations()


class TestFuelPlugin(unittest.TestCase):
    """Tests that make sure the plugin is being discovered well."""

    def test_settingsAreDiscovered(self):
        cs = caseSettings.Settings()
        nm = settings.CONF_CIRCULAR_RING_ORDER
        self.assertEqual(cs[nm], "angle")

        setting = cs.getSetting(nm)
        self.assertIn("distance", setting.options)


def addSomeDetailAssemblies(hist, assems):
    for a in assems:
        hist.detailAssemblyNames.append(a.getName())


if __name__ == "__main__":
    unittest.main()

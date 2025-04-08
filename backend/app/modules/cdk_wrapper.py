from __future__ import annotations

import os
from typing import List
from typing import Union

import pystow
from jpype import getDefaultJVMPath
from jpype import isJVMStarted
from jpype import JClass
from jpype import JPackage
from jpype import JVMNotFoundException
from jpype import startJVM


def setup_jvm():
    try:
        jvmPath = getDefaultJVMPath()
    except JVMNotFoundException:
        print("If you see this message, for some reason JPype cannot find jvm.dll.")
        print(
            "This indicates that the environment variable JAVA_HOME is not set properly."
        )
        print("You can set it or set it manually in the code")
        jvmPath = "Define/path/or/set/JAVA_HOME/variable/properly"

    print(jvmPath)

    if not isJVMStarted():
        paths = {
            "cdk-2.10": "https://github.com/cdk/cdk/releases/download/cdk-2.10/cdk-2.10.jar",
            "centres": "https://github.com/SiMolecule/centres/releases/download/1.0/centres.jar",
            }

        jar_paths = {
            key: str(pystow.join("CDK_Jar")) + f"/{key}.jar" for key in paths.keys()
        }
        for key, url in paths.items():
            if not os.path.exists(jar_paths[key]):
                pystow.ensure("CDK_Jar", url=url)

        startJVM("-ea", "-Xmx4096M", classpath=[jar_paths[key] for key in jar_paths])


setup_jvm()
cdk_base = "org.openscience.cdk"


def get_CDK_IAtomContainer(smiles: str):
    """This function takes the input SMILES and creates a CDK IAtomContainer.

    Args:
        smiles (str): SMILES string as input.

    Returns:
        mol (object): IAtomContainer with CDK.
    """
    SCOB = JClass(cdk_base + ".silent.SilentChemObjectBuilder")
    SmilesParser = JClass(
        cdk_base + ".smiles.SmilesParser",
    )(SCOB.getInstance())
    molecule = SmilesParser.parseSmiles(smiles)
    return molecule


def get_CDK_SDG(molecule: any):
    """This function takes the input IAtomContainer and Creates a.

    Structure Diagram Layout using the CDK.

    Args:
        molecule (IAtomContainer): molecule given by the user.

    Returns:
        mol object: mol object with CDK SDG.
    """
    StructureDiagramGenerator = JClass(
        cdk_base + ".layout.StructureDiagramGenerator",
    )()
    StructureDiagramGenerator.generateCoordinates(molecule)
    molecule_ = StructureDiagramGenerator.getMolecule()

    return molecule_


def get_CDK_SDG_mol(molecule: any, V3000=False) -> str:
    """Returns a mol block string with Structure Diagram Layout for the given.

    SMILES.

    Args:
        molecule (IAtomContainer): molecule given by the user.
        V3000 (bool, optional): Option to return V3000 mol. Defaults to False.

    Returns:
        str: CDK Structure Diagram Layout mol block.
    """
    StringW = JClass("java.io.StringWriter")()
    moleculeSDG = get_CDK_SDG(molecule)
    SDFW = JClass(cdk_base + ".io.SDFWriter")(StringW)
    SDFW.setAlwaysV3000(V3000)
    SDFW.write(moleculeSDG)
    SDFW.flush()
    mol_str = str(StringW.toString())
    return mol_str


def get_cip_annotation(molecule: any) -> str:
    """Return the CIP (Cahn–Ingold–Prelog) annotations using the CDK CIP.

    toolkit.

    This function takes a SMILES (Simplified Molecular Input Line Entry System) string
    as input and returns a CIP annotated molecule block using the CDK CIP toolkit.

    Args:
        molecule (IAtomContainer): molecule given by the user.

    Returns:
        str: A CIP annotated molecule block.
    """
    SDGMol = get_CDK_SDG(molecule)
    centres_base = "com.simolecule.centres"
    Cycles = JClass(cdk_base + ".graph.Cycles")
    IBond = JClass(cdk_base + ".interfaces.IBond")
    IStereoElement = JClass(cdk_base + ".interfaces.IStereoElement")
    Stereocenters = JClass(cdk_base + ".stereo.Stereocenters")
    StandardGenerator = JClass(
        cdk_base + ".renderer.generators.standard.StandardGenerator",
    )

    BaseMol = JClass(centres_base + ".BaseMol")
    CdkLabeller = JClass(centres_base + ".CdkLabeller")
    Descriptor = JClass(centres_base + ".Descriptor")

    stereocenters = Stereocenters.of(SDGMol)
    for atom in SDGMol.atoms():
        if (
            stereocenters.isStereocenter(atom.getIndex())
            and stereocenters.elementType(atom.getIndex())
            == Stereocenters.Type.Tetracoordinate
        ):
            atom.setProperty(StandardGenerator.ANNOTATION_LABEL, "(?)")

    # Iterate over bonds
    for bond in SDGMol.bonds():
        if bond.getOrder() != IBond.Order.DOUBLE:
            continue
        begIdx = bond.getBegin().getIndex()
        endIdx = bond.getEnd().getIndex()
        if (
            stereocenters.elementType(
                begIdx,
            )
            == Stereocenters.Type.Tricoordinate
            and stereocenters.elementType(endIdx) == Stereocenters.Type.Tricoordinate
            and stereocenters.isStereocenter(begIdx)
            and stereocenters.isStereocenter(endIdx)
        ):
            # Check if not in a small ring <7
            if Cycles.smallRingSize(bond, 7) == 0:
                bond.setProperty(StandardGenerator.ANNOTATION_LABEL, "(?)")

    # no defined stereo?
    if not SDGMol.stereoElements().iterator().hasNext():
        return SDGMol

    # Call the Java method
    CdkLabeller.label(SDGMol)

    # Update to label appropriately for racemic and relative stereochemistry
    for se in SDGMol.stereoElements():
        if se.getConfigClass() == IStereoElement.TH and se.getGroupInfo() != 0:
            focus = se.getFocus()
            label = focus.getProperty(BaseMol.CIP_LABEL_KEY)
            if (
                isinstance(label, Descriptor)
                and label != Descriptor.ns
                and label != Descriptor.Unknown
            ):
                if (se.getGroupInfo() & IStereoElement.GRP_RAC) != 0:
                    inv = None
                    if label == Descriptor.R:
                        inv = Descriptor.S
                    elif label == Descriptor.S:
                        inv = Descriptor.R
                    if inv is not None:
                        focus.setProperty(
                            BaseMol.CIP_LABEL_KEY,
                            label.toString() + inv.name(),
                        )
                elif (se.getGroupInfo() & IStereoElement.GRP_REL) != 0:
                    if label == Descriptor.R or label == Descriptor.S:
                        focus.setProperty(
                            BaseMol.CIP_LABEL_KEY,
                            label.toString() + "*",
                        )

    # Iterate over atoms
    for atom in SDGMol.atoms():
        if atom.getProperty(BaseMol.CONF_INDEX) is not None:
            atom.setProperty(
                StandardGenerator.ANNOTATION_LABEL,
                StandardGenerator.ITALIC_DISPLAY_PREFIX
                + atom.getProperty(BaseMol.CONF_INDEX).toString(),
            )
        elif atom.getProperty(BaseMol.CIP_LABEL_KEY) is not None:
            atom.setProperty(
                StandardGenerator.ANNOTATION_LABEL,
                StandardGenerator.ITALIC_DISPLAY_PREFIX
                + atom.getProperty(BaseMol.CIP_LABEL_KEY).toString(),
            )

    # Iterate over bonds
    for bond in SDGMol.bonds():
        if bond.getProperty(BaseMol.CIP_LABEL_KEY) is not None:
            bond.setProperty(
                StandardGenerator.ANNOTATION_LABEL,
                StandardGenerator.ITALIC_DISPLAY_PREFIX
                + bond.getProperty(BaseMol.CIP_LABEL_KEY).toString(),
            )

    return SDGMol


def get_CXSMILES(molecule: any) -> str:
    """Generate CXSMILES representation with 2D atom coordinates from the.

    given.

    SMILES.

    Args:
        molecule (IAtomContainer): molecule given by the user.

    Returns:
        str: CXSMILES representation with 2D atom coordinates.
    """
    SDGMol = get_CDK_SDG(molecule)
    SmiFlavor = JClass(cdk_base + ".smiles.SmiFlavor")
    SmilesGenerator = JClass(cdk_base + ".smiles.SmilesGenerator")(
        SmiFlavor.Absolute | SmiFlavor.CxSmilesWithCoords,
    )
    CXSMILES = SmilesGenerator.create(SDGMol)
    return str(CXSMILES)


def get_canonical_SMILES(molecule: any) -> str:
    """Generate Canonical SMILES representation with 2D atom coordinates from.

    the given SMILES.

    Args:
        molecule (IAtomContainer): molecule given by the user.

    Returns:
        str: Canonical SMILES representation with 2D atom coordinates.
    """
    SDGMol = get_CDK_SDG(molecule)
    SmiFlavor = JClass(cdk_base + ".smiles.SmiFlavor")
    SmilesGenerator = JClass(
        cdk_base + ".smiles.SmilesGenerator",
    )(SmiFlavor.Absolute)
    CanonicalSMILES = SmilesGenerator.create(SDGMol)
    return str(CanonicalSMILES)

def read_molfile_as_cdk_mol(molfile_string: str) -> Any:
    """
    Convert a molfile string directly to a CDK molecule object with its existing coordinates.
    
    Args:
        molfile_string: String representation of a molfile
        
    Returns:
        CDK IAtomContainer molecule with existing coordinates
        
    Raises:
        ValueError: If the molfile cannot be parsed
    """
    if not molfile_string:
        raise ValueError("No molfile content provided")
    
    try:
        # Import necessary Java classes
        from jpype import JClass, java
        
        cdk_base = "org.openscience.cdk"
        SCOB = JClass(cdk_base + ".silent.SilentChemObjectBuilder")
        
        # Create Java string reader
        string_reader = java.io.StringReader(molfile_string)
        
        # Create a reader
        reader = JClass(cdk_base + ".io.MDLV2000Reader")(string_reader)
        
        # Read the molecule
        molecule = reader.read(SCOB.getInstance().newAtomContainer())
        
        # Verify the molecule was created
        if molecule is None:
            raise ValueError("Failed to parse molfile")
        
        # Close the reader
        reader.close()
        
        return molecule
    except Exception as e:
        raise ValueError(f"Error parsing molfile: {str(e)}")

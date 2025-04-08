from __future__ import annotations

import xml.etree.ElementTree as ET
import io
import base64
from typing import Dict, Any, Union, Tuple, Optional, Literal

from fastapi import HTTPException, status

# Import CDK wrapper functions
from app.modules.cdk_wrapper import (
    get_CDK_IAtomContainer,
    get_CDK_SDG,
    get_cip_annotation,
    read_molfile_as_cdk_mol
)

# Only import cairosvg if needed for PNG conversion
try:
    import cairosvg
    CAIROSVG_AVAILABLE = True
except ImportError:
    CAIROSVG_AVAILABLE = False


def get_cdk_depiction(
    molecule: Any,
    mol_size: Tuple[int, int] = (512, 512),
    rotate: float = 0,
    kekulize: bool = True,
    cip: bool = True,
    unicolor: bool = False,
    highlight: str = "",
    transparent: bool = False,
    add_coords: bool = True,
) -> str:
    """
    Generate a 2D depiction of a molecule using CDK's DepictionGenerator.
    
    Args:
        molecule: CDK IAtomContainer molecule object
        mol_size: Size of the output image (width, height)
        rotate: Rotation angle in degrees
        kekulize: Whether to kekulize the molecule
        cip: Whether to add CIP stereochemistry annotations
        unicolor: Whether to use a single color for all atoms
        highlight: SMARTS pattern to highlight
        transparent: Whether to use transparent background
        add_coords: Whether to generate 2D coordinates if not present
        
    Returns:
        SVG string representation of the molecule
    
    Raises:
        ValueError: If molecule cannot be processed
    """
    try:
        # Import necessary Java classes
        from jpype import JClass
        
        cdk_base = "org.openscience.cdk"
        StandardGenerator = JClass(cdk_base + ".renderer.generators.standard.StandardGenerator")
        Color = JClass("java.awt.Color")
        UniColor = JClass(cdk_base + ".renderer.color.UniColor")
        CDK2DAtomColors = JClass(cdk_base + ".renderer.color.CDK2DAtomColors")()
        Kekulization = JClass(cdk_base + ".aromaticity.Kekulization")
        SmartsPattern = JClass(cdk_base + ".smarts.SmartsPattern")
        SCOB = JClass(cdk_base + ".silent.SilentChemObjectBuilder")
        
        # Configure the depiction generator
        if unicolor:
            depiction_generator = (
                JClass(cdk_base + ".depict.DepictionGenerator")()
                .withSize(mol_size[0], mol_size[1])
                .withParam(StandardGenerator.StrokeRatio.class_, 1.0)
                .withAnnotationColor(Color.BLACK)
                .withParam(StandardGenerator.AtomColor.class_, UniColor(Color.BLACK))
                .withFillToFit()
            )
        else:
            depiction_generator = (
                JClass(cdk_base + ".depict.DepictionGenerator")()
                .withAtomColors(CDK2DAtomColors)
                .withSize(mol_size[0], mol_size[1])
                .withParam(StandardGenerator.StrokeRatio.class_, 1.0)
                .withFillToFit()
            )
        
        # Set background color
        if transparent:
            # Use transparent background
            depiction_generator = depiction_generator.withBackgroundColor(None)
        else:
            # Use white background
            depiction_generator = depiction_generator.withBackgroundColor(Color.WHITE)
        
        # Apply CIP stereochemistry annotations if requested
        if cip:
            sdg_mol = get_cip_annotation(molecule)
        else:
            # Check if coordinates need to be generated
            if add_coords:
                sdg_mol = get_CDK_SDG(molecule)
            else:
                sdg_mol = molecule
        
        if not sdg_mol:
            raise ValueError("Failed to process molecule for depiction")
        
        # Apply kekulization if requested
        if kekulize:
            try:
                Kekulization.kekulize(sdg_mol)
            except Exception as e:
                print(f"Kekulization error: {str(e)}")
        
        # Apply rotation if requested
        if rotate != 0:
            point = JClass(cdk_base + ".geometry.GeometryTools").get2DCenter(sdg_mol)
            JClass(cdk_base + ".geometry.GeometryTools").rotate(
                sdg_mol,
                point,
                (rotate * JClass("java.lang.Math").PI / 180.0),
            )
        
        # Apply highlighting if requested
        if highlight and highlight.strip():
            try:
                tmp_pattern = SmartsPattern.create(highlight, SCOB.getInstance())
                SmartsPattern.prepare(sdg_mol)
                tmp_mappings = tmp_pattern.matchAll(sdg_mol)
                tmp_substructures = tmp_mappings.toSubstructures()
                light_blue = Color(173, 216, 230)
                depiction_generator = depiction_generator.withHighlight(
                    tmp_substructures, light_blue
                ).withOuterGlowHighlight()
            except Exception as e:
                print(f"Highlighting error: {str(e)}")
        
        # Generate SVG
        mol_image_svg = (
            depiction_generator.depict(sdg_mol)
            .toSvgStr("px")
            .getBytes()
        )
        
        # Parse and convert to string
        encoded_image = ET.tostring(
            ET.fromstring(mol_image_svg),
            encoding="unicode",
        )
        
        return encoded_image
    
    except Exception as e:
        raise ValueError(f"Error generating CDK depiction: {str(e)}")


def generate_depiction(
    smiles: str = None,
    molfile: str = None,
    engine: Literal["cdk", "rdkit"] = "cdk",
    mol_size: Tuple[int, int] = (512, 512),
    rotate: float = 0,
    kekulize: bool = True,
    cip: bool = True,
    unicolor: bool = False,
    highlight: str = "",
    transparent: bool = False,
    format: Literal["svg", "png", "base64"] = "svg",
    use_molfile_directly: bool = False,
) -> Dict[str, Any]:
    """
    Generate a molecular depiction using the CDK engine.
    
    Args:
        smiles: SMILES string (optional if molfile is provided)
        molfile: Molfile string (optional if SMILES is provided)
        engine: Ignored - always uses CDK
        mol_size: Size of the output image (width, height)
        rotate: Rotation angle in degrees
        kekulize: Whether to kekulize the molecule
        cip: Whether to add CIP stereochemistry annotations
        unicolor: Whether to use a single color for all atoms
        highlight: SMARTS pattern to highlight
        transparent: Whether to use transparent background
        format: Output format (svg, png, or base64-encoded png)
        use_molfile_directly: Whether to use molfile directly with CDK (skip coordinate generation)
        
    Returns:
        Dictionary containing the depiction and metadata
        
    Raises:
        HTTPException: If input or parameters are invalid
    """
    # Validate input
    if not smiles and not molfile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either SMILES or molfile must be provided"
        )
    
    # Always use CDK
    engine = "cdk"
    
    try:
        svg_string = None
        
        # For CDK engine
        if molfile and (not smiles or use_molfile_directly):
            # Use molfile directly with CDK - this is the preferred method for MolNexTR output
            try:
                # Directly read molfile as CDK molecule
                cdk_molecule = read_molfile_as_cdk_mol(molfile)
                
                # Generate depiction without adding coordinates - use existing ones
                svg_string = get_cdk_depiction(
                    cdk_molecule,
                    mol_size=mol_size,
                    rotate=rotate,
                    kekulize=kekulize,
                    cip=cip,
                    unicolor=unicolor,
                    highlight=highlight,
                    transparent=transparent,
                    add_coords=False  # Don't regenerate coordinates
                )
            except Exception as e:
                print(f"Error using molfile directly with CDK: {str(e)}")
                
                # Fallback to using SMILES if available
                if smiles:
                    cdk_molecule = get_CDK_IAtomContainer(smiles)
                    svg_string = get_cdk_depiction(
                        cdk_molecule,
                        mol_size=mol_size,
                        rotate=rotate,
                        kekulize=kekulize,
                        cip=cip,
                        unicolor=unicolor,
                        highlight=highlight,
                        transparent=transparent,
                        add_coords=True
                    )
                else:
                    raise ValueError(f"Failed to parse molfile and no SMILES fallback available: {str(e)}")
        else:
            # Use SMILES to create CDK molecule and generate coordinates
            cdk_molecule = get_CDK_IAtomContainer(smiles)
            svg_string = get_cdk_depiction(
                cdk_molecule,
                mol_size=mol_size,
                rotate=rotate,
                kekulize=kekulize,
                cip=cip,
                unicolor=unicolor,
                highlight=highlight,
                transparent=transparent,
                add_coords=True
            )
        
        # Convert to requested format
        if format == "svg":
            # Return SVG directly
            return {
                "format": "svg",
                "engine": engine,
                "depiction": svg_string
            }
        else:
            # Convert SVG to PNG using cairosvg if available
            try:
                if not CAIROSVG_AVAILABLE:
                    return {
                        "format": "svg",
                        "engine": engine,
                        "depiction": svg_string,
                        "warning": "cairosvg not available, returning SVG instead"
                    }
                
                png_data = cairosvg.svg2png(bytestring=svg_string.encode())
                
                # Return as base64 if requested
                if format == "base64":
                    base64_data = base64.b64encode(png_data).decode()
                    return {
                        "format": "base64",
                        "engine": engine,
                        "depiction": base64_data
                    }
                else:
                    # Return binary PNG data
                    return {
                        "format": "png",
                        "engine": engine,
                        "depiction": png_data
                    }
            except Exception as e:
                # Fall back to SVG if PNG conversion fails
                return {
                    "format": "svg",
                    "engine": engine,
                    "depiction": svg_string,
                    "warning": f"PNG conversion failed: {str(e)}, returning SVG instead"
                }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating depiction: {str(e)}"
        )
import json
import os

import cv2
import numpy as np

import darsia

# def test_color_correction():
#
#    # Define path to image
#    image = f"{os.path.dirname(__file__)}/../examples/images/baseline.jpg"
#
#    # ! ---- Setup the manual color correction
#
#    # Need to specify the pixel coordines in (x,y), i.e., (col,row) format, of the
#    # marks on the color checker.
#    roi_cc = np.array(
#        [
#            [154, 176],
#            [222, 176],
#            [222, 68],
#            [154, 68],
#        ]
#    )
#    color_correction = darsia.ColorCorrection(
#        roi=roi_cc,
#    )
#
#    # Create the color correction and apply it at initialization of image class
#    corrected_image = darsia.Image(
#        image,
#        color_correction=color_correction,
#        width=2.8,
#        height=1.5,
#    )
#
#    # Load reference image
#    reference_image = np.load(
#        "./reference/color_corrected_baseline.npy", allow_pickle=True
#    )
#
#    # Make a direct comparison
#    assert np.all(np.isclose(reference_image, corrected_image.img))


def read_test_image(img_id: str) -> tuple[np.ndarray, dict]:
    """Centralize reading of test image.

    Returns:
        array: image array in RGB format read from jpg.
        dict: metadata

    """

    # ! ---- Define image array in RGB format
    path = f"{os.path.dirname(__file__)}/../../examples/images/{img_id}.jpg"
    array = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)

    # ! ---- Define some metadata corresponding to the input array
    info = {
        "dim": 2,
        "orientation": "ij",
    }

    return array, info


def test_color_correction():
    """Test color correction, effectively converting from BGR to RGB."""

    # ! ---- Fetch test image
    array, info = read_test_image("baseline")

    # ! ---- Setup color correction

    # Need to specify the pixel coordines in (x,y), i.e., (col,row) format, of the
    # marks on the color checker.
    config = {
        "roi": np.array(
            [
                [154, 176],
                [222, 176],
                [222, 68],
                [154, 68],
            ]
        )
    }
    color_correction = darsia.ColorCorrection(**config)

    # ! ---- Define corrected image

    image = darsia.GeneralImage(img=array, transformations=[color_correction], **info)

    # ! ---- Compare corrected image with reference

    # Load reference image
    reference_image = np.load(
        "../reference/color_corrected_baseline.npy", allow_pickle=True
    )

    # Make a direct comparison
    assert np.all(np.isclose(reference_image, image.img))


def test_curvature_correction():
    """Test of curvature correction applied to a numpy array. The correction
    routine contains all relevant operations, incl. bulging, stretching, and
    cropping."""

    # ! ---- Fetch test image
    array, info = read_test_image("co2_2")

    # ! ---- Setup correction

    # Fetch config file, holding info to several correction routines.
    config_path = f"{os.path.dirname(__file__)}/../../examples/images/config.json"
    with open(config_path, "r") as openfile:
        config = json.load(openfile)

    # Define curvature correction object, initiated with config file
    curvature_correction = darsia.CurvatureCorrection(config=config["curvature"])

    # ! ---- Define corrected image

    image = darsia.GeneralImage(
        img=array, transformations=[curvature_correction], **info
    )

    # ! ---- Compare corrected image with reference

    reference_image = np.load(
        "../reference/curvature_corrected_co2_2.npy", allow_pickle=True
    )
    assert np.all(np.isclose(reference_image, image.img))


def test_drift_correction():
    """Test the relative aligning of images via a drift."""

    # ! ---- Fetch test images
    original_array, info = read_test_image("baseline")
    original_image = darsia.GeneralImage(img=original_array, **info)

    # ! ---- Define drift correction
    roi = (slice(0, 600), slice(0, 600))
    drift_correction = darsia.DriftCorrection(base=original_image, roi=roi)

    # ! ---- Apply affine transformation
    affine_matrix = np.array([[1, 0, 10], [0, 1, -6]]).astype(np.float32)
    translated_array = cv2.warpAffine(
        original_array, affine_matrix, tuple(reversed(original_array.shape[:2]))
    )
    corrected_image = darsia.GeneralImage(
        img=translated_array, transformations=[drift_correction], **info
    )

    # ! ---- Compare original and corrected image, but remove the boundary.
    assert np.all(
        np.isclose(
            original_image.img[10:-10, 10:-10], corrected_image.img[10:-10, 10:-10]
        )
    )
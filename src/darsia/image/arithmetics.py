"""Utils for non-standard arithmetics of images,
as weighted superposition.

"""

from typing import Union

import cv2
import numpy as np

import darsia


def weight(img: darsia.Image, weight: Union[float, int, darsia.Image]) -> darsia.Image:
    """Scalar or element-wise weight of images.

    Args:
        img (darsia.Image): image.
        weight (float or Image): weight, either constant, or heterogeneous provided through
            an image with local coordinates (need to be the same as for the input image).

    Returns:
        Image: weighted image.

    """
    weighted_img = img.copy()
    if isinstance(weight, float) or isinstance(weight, int):
        weighted_img.img *= weight
    elif isinstance(weight, darsia.Image):
        # TODO add safety check whether the coordinate systems are the same
        space_dim = img.space_dim
        assert np.isclose(img.origin, weight.origin)
        assert np.isclose(img.dimensions, weight.dimensions)
        assert len(weight.img.shape) == space_dim

        # Reshape if needed.
        if img.img.shape[:space_dim] != weight.img.shape[:space_dim]:
            if img.space_dim == 2:
                weight.img = cv2.resize(
                    weight.img,
                    tuple(reversed(img.img.shape[:2])),
                    interpolation=cv2.INTER_LINEAR,
                )
            else:
                raise NotImplementedError

        # Rescale
        weighted_img.img = np.mulitply(weighted_img.img, weight.img)

    return weighted_img


def superpose(images: list[darsia.Image]) -> darsia.Image:
    """Superposition of images with possibly incompatible coordinatesystems.

    Args:
        images (list of images): images

    Returns:
        Image: superposed image.

    """
    # ! ---- Commonalities.

    # Safety checks
    assert all([img.space_dim == images[0].space_dim for img in images])
    assert all([img.indexing == images[0].indexing for img in images])
    assert all([img.series == images[0].series for img in images])
    assert all([isinstance(img, type(images[0])) for img in images])
    assert all([img.original_dtype == images[0].original_dtype for img in images])

    # TODO include time, for now assume it is the same...
    # print([img.date for img in images])

    # Fetch common specs
    # TODO use meta and update? fetch from images[0]
    space_dim = images[0].space_dim
    indexing = images[0].indexing
    series = images[0].series

    # TODO double check
    date = images[0].date
    time = images[0].time

    # TODO make the following two part of metadata? better not...
    # they are directly encoded in Image and array...
    dtype = images[0].original_dtype
    ImageType = type(images[0])

    # ! ---- Determine the meta data

    # Determine the common origin and opposite corner (as Cartesian coordinates)
    collection_origin = np.vstack(tuple(img.origin for img in images))
    collection_opposite_corner = np.vstack(tuple(img.opposite_corner for img in images))
    origin = []
    opposite_corner = []
    for i in range(space_dim):
        # In case the axis follows a different orientation than
        # the corresponding cartesian axis, the maximal coordinate
        # has to be chosen (e.g., y-axis in 2d), minimal otherwise.
        _, revert = darsia.interpret_indexing("xyz"[i], indexing)
        if revert:
            origin.append(np.max(collection_origin[:, i]))
            opposite_corner.append(np.min(collection_opposite_corner[:, i]))
        else:
            origin.append(np.min(collection_origin[:, i]))
            opposite_corner.append(np.max(collection_opposite_corner[:, i]))

    # Determine resulting dimensions in matrix indexing
    cartesian_dimensions = [
        abs(opposite_corner[i] - origin[i]) for i in range(space_dim)
    ]
    to_matrix_indexing = [
        darsia.interpret_indexing("ijk"[i], "xyz"[:space_dim])[0]
        for i in range(space_dim)
    ]
    dimensions = [cartesian_dimensions[i] for i in to_matrix_indexing]

    meta = {
        "dim": space_dim,
        "indexing": indexing,
        "dimensions": dimensions,
        "origin": origin,
        "series": series,
        "date": date,
        "time": time,
    }

    # ! ---- Superpose the data

    # Find the correct shape and initialize image, and coordinatesystem
    collection_voxel_size = np.vstack(tuple(img.voxel_size for img in images))
    voxel_size = np.min(collection_voxel_size, axis=0)
    shape = tuple(
        np.ceil(dimensions[i] / voxel_size[i]).astype(int) for i in range(space_dim)
    )
    img_arr = np.zeros(shape, dtype=dtype)
    image = ImageType(img=img_arr, **meta)

    # Successively add images to the right voxels - essentially use resample
    # Approach from imread_from_vtu, but now voxel grids are provided.
    for img in images:
        # Get array and shape
        array = img.img
        rows, cols = array.shape

        # Use corners as pts_src
        pts_src = np.array(
            [
                [0, 0],
                [rows, 0],
                [rows, cols],
                [0, cols],
            ]
        )

        # Get origin and opposite corner for img
        origin = img.origin
        opposite_corner = img.opposite_corner

        # Use image.coordinatesystem to retrieve pts_dst
        mapped_voxel_origin = image.coordinatesystem.voxel(origin)
        mapped_voxel_opposite_corner = image.coordinatesystem.voxel(opposite_corner)

        pts_dst = np.array(
            [
                [mapped_voxel_origin[0], mapped_voxel_origin[1]],
                [mapped_voxel_opposite_corner[0], mapped_voxel_origin[1]],
                [mapped_voxel_opposite_corner[0], mapped_voxel_opposite_corner[1]],
                [mapped_voxel_origin[0], mapped_voxel_opposite_corner[1]],
            ]
        )

        # Warp array
        warped_array = darsia.extract_quadrilateral_ROI(
            img_src=array,
            pts_src=pts_src,
            pts_dst=pts_dst,
            indexing="matrix",
            interpolation="inter_area",
            shape=shape,
        )

        # Add warped_array to image.img
        image.img += warped_array

    return image
"""Module containing routines to read images from file to DarSIA. Several file types
are supported:

* optical images: *jpg, *jpeg, *png, *tif, *tiff
* DICOM images: *dcm
* simulation data: anything which can be read by meshio, e.g. *vtu
* numpy images: *npy

"""

from __future__ import annotations

from datetime import datetime
from operator import itemgetter
from pathlib import Path
from subprocess import check_output
from typing import Optional, Union

import cv2
import numpy as np
import pydicom
from PIL import Image as PIL_Image
from scipy.interpolate import NearestNDInterpolator

import darsia

# ! ---- Interface to subroutines - general reading routine


def imread(path: Union[str, Path, list[str], list[Path]], **kwargs) -> darsia.Image:
    """Determine and call reading routine depending on filetype.
    Provide interface for numpy arrays, standard optical image formats,
    dicom images, and vtu images.

    Args:
        path (str, Path or list of such): path(s) to file(s).
        kwargs: keyword arguments tailored to the file format.

    Returns:
        Image, or list of such: image of collection of images.

    """

    # Convert to path
    if isinstance(path, list):
        path = [Path(p) for p in path]
    elif isinstance(path, str):
        path = Path(path)

    # Extract content of folder if folder provided.
    if isinstance(path, Path) and path.is_dir():
        path = sorted(list(path.glob("*")))
    elif isinstance(path, list) and all([p.is_dir() for p in path]):
        tmp_path = []
        for p in path:
            tmp_path = tmp_path + list(p.glob("*"))
        path = sorted(tmp_path)

    # Check if files exist
    if isinstance(path, list):
        assert all([p.exists() for p in path]), "Not all files exist."
    else:
        assert path.exists(), f"File {path} does not exist."

    # Determine file type of images
    suffix = kwargs.get("suffix", None)

    if suffix is None:
        if isinstance(path, list):
            suffix = path[0].suffix
            assert all([p.suffix == suffix for p in path])
        else:
            suffix = path.suffix

        # Use lowercase for robustness
        suffix = str(suffix).lower()

    # Depending on the ending run the corresponding routine.
    if suffix == ".npy":
        return imread_from_numpy(path, **kwargs)
    elif suffix == ".npz":
        return imread_from_npz(path)
    elif suffix in [".jpg", ".jpeg", ".png", ".tif", ".tiff"]:
        return imread_from_optical(path, **kwargs)
    elif suffix in [".dcm"]:
        return imread_from_dicom(path, **kwargs)
    elif suffix in [".vtu"]:
        return imread_from_vtu(path, **kwargs)
    else:
        raise NotImplementedError(f"Filetype {suffix} not supported.")


def imread_from_bytes(
    data: bytes,
    transformations: Optional[list] = None,
    **kwargs,
) -> darsia.Image:
    """Initialization of Image by reading from byte string.

    Args:
        data (bytes): byte string of image.
        transformations (list of callables): transformations.
        kwargs: keyword arguments.

    Returns:
        darsia.Image: image; scalar or optical, depending on the number of channels.

    """
    # Read image from byte string, convert to RGB
    array = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)

    if len(array.shape) == 3 and array.shape[-1] == 3:
        # If multichromatic, convert to RGB (Assume BGR format from cv2)
        array = cv2.cvtColor(array, cv2.COLOR_BGR2RGB)
        return darsia.OpticalImage(img=array, transformations=transformations, **kwargs)
    elif len(array.shape) == 2:
        return darsia.ScalarImage(img=array, transformations=transformations, **kwargs)
    elif len(array.shape) == 3 and array.shape[-1] == 1:
        return darsia.ScalarImage(
            img=array[..., 0], transformations=transformations, **kwargs
        )
    else:
        raise NotImplementedError


# ! ---- Numpy arrays


def imread_from_numpy(
    path: Union[Path, list[Path]], **kwargs
) -> Union[darsia.Image, list[darsia.Image]]:
    """Converter from npy format to darsia.Image.

    Args:
        path (Path or list of Path): path(s) to npy files.
        keyword arguments:


    """
    if isinstance(path, list):
        raise NotImplementedError

    array = np.load(path, allow_pickle=True)
    image = darsia.Image(array, **kwargs)
    return image


def imread_from_npz(path: Union[Path, list[Path]]) -> darsia.Image:
    """Converter from npz format to darsia.Image.

    Args:
        path (Path or list of Path): path(s) to npz files.

    """
    npzdata = np.load(path, allow_pickle=True)
    array = npzdata["array"]
    metadata = npzdata["metadata"].item()
    image = darsia.Image(array, **metadata)
    return image


# ! ---- Optical images


def imread_from_optical(
    path: Union[Path, list[Path]],
    time: Optional[Union[int, float, list]] = None,
    transformations: Optional[list] = None,
    **kwargs,
) -> Union[darsia.OpticalImage, list[darsia.OpticalImage]]:
    """Reading functionality from jpg, png, tif format to optical images.

    Args:
        path (Path or list of such): path(s) to image(s).
        time (scalar or list of such): user-specified physical times;
            automatically detected from metadata if 'None'.
        transformations (list of callables): transformations for 2d images.
        keyword arguments:
            date (datetime): custom datetime; otherwise read from metadata
            color_space (str): custom color space; RGB is assumed otherwise
            any arguments accepted by Image

    Returns:
        OpticalImage (or list of such): converted image, list of such, or
            space-time image, depending on the flag 'series'.

    """
    # TODO check method for grayscale images. shape of array?

    if isinstance(path, Path):
        # Read single image incl. date from metadata of the image
        array, date = _read_single_optical_image(path)

        # Use the date only if not provided separately
        if "date" not in kwargs:
            kwargs["date"] = date

        # Enhance metadata
        kwargs["series"] = False
        if "color_space" not in kwargs:
            kwargs["color_space"] = "RGB"

        # Define image
        image = darsia.OpticalImage(
            img=array,
            time=time,
            transformations=transformations,
            **kwargs,
        ).img_as(float)

        return image

    elif isinstance(path, list):
        # Collection of images

        # Read from file
        data = [_read_single_optical_image(p) for p in path]

        # Create a space-time optical image through stacking along the time axis
        space_time_array = np.stack([d[0] for d in data], axis=2)
        dates = [d[1] for d in data]

        # Fix metadata
        kwargs["series"] = True
        kwargs["color_space"] = "RGB"

        # Define image
        image = darsia.OpticalImage(
            img=space_time_array,
            date=dates,
            time=time,
            transformations=transformations,
            **kwargs,
        ).img_as(float)
        return image

    else:
        raise NotImplementedError


def _read_single_optical_image(path: Path) -> tuple[np.ndarray, Optional[datetime]]:
    """Utility function for setting up a single optical image.

    Args:
        path (Path): path to single optical image.

    Returns:
        np.ndarray: data array in RGB format
        date (optional): date

    """
    # Read image and convert to RGB and float ([0,1])
    array = cv2.cvtColor(cv2.imread(str(path), cv2.IMREAD_UNCHANGED), cv2.COLOR_BGR2RGB)

    # Prefered: Read time from exif metafile.
    pil_img = PIL_Image.open(path)
    exif = pil_img.getexif()
    if exif.get(306) is not None:
        # Hardcoded way of retrieving the datetime of "2022:08:29 23:10:27"
        date = datetime.strptime(exif.get(306), "%Y:%m:%d %H:%M:%S")
    else:
        date = None

    # Alternatively, use terminal output.
    # Credit to: https://stackoverflow.com/questions/27929025/...
    # ...exif-python-pil-return-empty-dictionary
    if date is None:
        try:
            # The following code requires the ImageMagick package. If not installed,
            # the following line will raise a NotFileFoundError.
            output = check_output(f"identify -verbose {str(path)}".split())
            meta = {}
            for line in output.splitlines()[:-1]:
                spl = line.decode().split(":", 1)
                k, v = spl
                meta[k.lstrip()] = v.strip()

            date_with_info = meta["date"]
            spl = date_with_info.split(":", 1)
            # Hardcoded way of retrieving the datetime of "2022-10-12T11:02:40+02:00"
            date = datetime.strptime(spl[1][1:], "%Y-%m-%dT%H:%M:%S%z")
        except FileNotFoundError:
            print(
                "Warning: No exif metafile found. "
                "Please install ImageMagick to read metadata from terminal."
            )

    return array, date


# ! ---- DICOM images


def imread_from_dicom(
    path: Union[Path, list[Path]],
    dim: int = 2,
    transformations: Optional[list] = None,
    **kwargs,
) -> Union[darsia.ScalarImage, list[darsia.ScalarImage]]:
    """Initialization of Image by reading from DICOM format.

    Assumptions: Coordinate systems in DICOM format are organized in an ijk format,
    which is different from the ijk format used for general images. DICOM images
    come in slices, and conventionally the coordinate system is associated relatively
    to the object to be scanned, which is not the coordinate system according to
    gravity, since objects usually lie horizontally in a medical scanner. In DarSIA we
    translate to the standard Cartesian coordinate system such that the z-coordinate is
    aligned with the gravitational force. Therefore the ijk indexing of standard DICOM
    images is not consistent with the matrix indexing of darsia.Image. The
    transformation of coordinate axes is performed here.

    Args:
        path (Path, or list of such): path to dicom stacks
        dim (int): spatial dimensionality of the images.
        transformations (list of callables): transformations.
        kwargs: keyword arguments.



    NOTE: Merely scalar data can be handled.

    Returns:
        darsia.Image: 3d space-time image

    Raises:
        ImportError: if pydicom is not installed

    """
    # ! ---- Image type

    # PYDICOM specific tags for addressing dicom data from dicom files
    tag_position = pydicom.tag.BaseTag(0x00200032)
    tag_rows = pydicom.tag.BaseTag(0x00280010)
    tag_cols = pydicom.tag.BaseTag(0x00280011)
    tag_pixel_size = pydicom.tag.BaseTag(0x00280030)
    tag_slice_thickness = pydicom.tag.BaseTag(0x00180050)
    tag_acquisition_date = pydicom.tag.BaseTag(0x00080022)
    tag_acquisition_time = pydicom.tag.BaseTag(0x00080032)
    # TODO
    # tag_number_slices = pydicom.tag.BaseTag(0x00540081)
    tag_rescale_intercept = pydicom.tag.BaseTag(0x00281052)
    tag_rescale_slope = pydicom.tag.BaseTag(0x00281053)
    # tag_series_description = pydicom.tag.BaseTag(
    #     0x0008103E
    # )  # TODO include as name for image

    # Good to have for future safety checks.
    # tag_number_time_slices = pydicom.tag.BaseTag(0x00540101)

    # ! ---- 1. Step: Get overview of number of images

    # Convert srcfile to a list of just a string.
    if not isinstance(path, list):
        path = [path]

    # Initialize arrays for DICOM data
    pixel_data = []  # actual signal
    slice_positions = []  # the position in page direction, i.e., of each slice.
    num_rows = []  # image size in row/z direction.
    num_cols = []  # image size in col/y direction.
    # num_slices = []  # image size in page/x direction # TODO rm
    acq_times = []  # acquisition time of samples
    acq_date_time_tuples = []  # acquision (date, time) of samples

    # Consider each dicom file by itself (each file is a sample and has to
    # be sorted into the larger picture.
    for p in path:
        # Read the dicom sample
        dataset = pydicom.dcmread(p)

        # Extract the actual signal.
        signal = dataset.pixel_array

        # Rescale
        intercept = dataset[tag_rescale_intercept].value
        slope = dataset[tag_rescale_slope].value
        rescaled_signal = intercept + slope * signal

        # NOTE: In practice, corrections used to reconstruct the DICOM images (decay,
        # dead time) do not need to be the same for all images. This is not taken care
        # of in DarSIA at the moment.

        # Store
        pixel_data.append(rescaled_signal)

        # Extract position for each slice.
        slice_positions.append(np.array(dataset[tag_position].value))

        # Extract number of datapoints in each direction.
        num_rows.append(dataset[tag_rows].value)
        num_cols.append(dataset[tag_cols].value)
        # TODO rm
        # if tag_number_slices in dataset:  # may only exist for 2d images
        #    num_slices.append(dataset[tag_number_slices].value)
        # else:
        #    num_slices.append(1)

        # Extract acquisition time for each slice
        acq_date_time_tuples.append(
            dataset[tag_acquisition_date].value + dataset[tag_acquisition_time].value
        )
        acq_times.append(dataset[tag_acquisition_time].value)

        # Extract pixel size - assume constant for all files - and assume info in mm
        conversion_mm_to_m = 10 ** (-3)
        voxel_size = np.zeros(dim)
        # pixels are assumed to have the same dimensions in both directions.
        voxel_size[:2] = np.array(dataset[tag_pixel_size].value) * conversion_mm_to_m
        if dim == 3:
            # k corresponds to the slice thickness
            voxel_size[2] = dataset[tag_slice_thickness].value * conversion_mm_to_m

    # Assume constant image size.
    assert all([num_rows[i] == num_rows[0] for i in range(len(num_rows))])
    assert all([num_cols[i] == num_cols[0] for i in range(len(num_cols))])
    # TODO rm
    # assert all([num_slices[i] == num_slices[0] for i in range(len(num_slices))])

    # ! ---- 2. Step: Sort input wrt datetime

    # Convert data to numpy arrays.
    voxel_data = np.stack(pixel_data, axis=2)  # comes in standard matrix indexing
    slice_positions = np.array(slice_positions)  # only used to sort slices.
    acq_times = np.array(acq_times)  # used to distinguish between images.

    # Convert date time strings to datetime format. Expect a data format for the input
    # as ('20210222133538.000'), where the first entry represent the date Feb 22, 2021,
    # and the second entry represents the time 13 hours, 35 minutes, and 38 seconds.
    # Sort the list of datetimes, starting with the earliest datetime.
    def datetime_conversion(date_time: str) -> datetime:
        return datetime.strptime(date_time[:14], "%Y%m%d%H%M%S")

    # Convert times to different formats, forcing uniqueness and search possibilties.
    acq_date_time_tuples = np.array(acq_date_time_tuples, dtype=object)
    unique_acq_dates = list(set(acq_date_time_tuples))
    times_indices = [
        (datetime_conversion(u), i) for i, u in enumerate(unique_acq_dates)
    ]
    sorted_times_indices = sorted(times_indices, key=itemgetter(0))
    sorted_times = [t for t, _ in sorted_times_indices]
    sorted_indices = [i for _, i in sorted_times_indices]

    # Determine varying axis in slice positions (assume same for all slices)
    varying_axis = int(np.argwhere(np.diff(slice_positions, axis=0)[0] != 0))
    num_slices = len(list(set(slice_positions[:, varying_axis])))

    # Group and sort data into the time frames, converting the 3d tensor
    # into a 4d img
    time = sorted_times
    shape = (num_rows[0], num_cols[0], num_slices, len(time))
    img = np.zeros(shape, dtype=voxel_data.dtype)
    for i, date_time in enumerate(sorted_times):
        # Fetch corresponding datetime in original format
        index = sorted_indices[i]
        unique_date_time = unique_acq_dates[index]

        # Fetch all frames corresponding to the current time frame
        time_frame = np.argwhere(acq_date_time_tuples == unique_date_time).flatten()

        # For each time frame, sort data in slice-direction (stored as third component)
        sorted_time_frame = np.argsort(slice_positions[time_frame, varying_axis])

        # Apply sorting to the time frames
        sorted_time_frame = time_frame[sorted_time_frame]

        # Store data at right time
        img[..., i] = voxel_data[..., sorted_time_frame]

    # Reduce to sufficient size in special cases
    if dim == 2:
        img = img[:, :, 0]

    # Automatically reduce to non space-time setting if only a single time step is accessible.
    series = img.shape[-1] > 1
    if not series:
        img = img[..., 0]
        time = time[0]

    # ! ---- 3. Convert to Image

    # Pick first position simply as origin
    # TODO need to choose max, min, etc., define functionality in coordinatesyste,
    origin = slice_positions[0]

    # Collect all meta information for a space time image
    dimensions = [voxel_size[i] * shape[i] for i in range(dim)]
    meta = {
        # "name": series_description[0],
        "space_dim": dim,
        "indexing": "ijk"[:dim],
        "dimensions": dimensions,
        "series": series,
        "date": time,
        "origin": origin,
    }

    # Full space time image
    return darsia.ScalarImage(img=img, transformations=transformations, **meta)


# ! ---- VTU images


def imread_from_vtu(
    path: Union[Path, list[Path]],
    key: str,
    shape: tuple[int],
    **kwargs,
) -> darsia.Image:
    """Reading routine for data readible with meshio.

    NOTE: Only for 1d and 2d vtu images. Actually since meshio is used here, any format
    should work, but it is only tested for vtu images.

    Includes mapping onto a pixelated grid.

    Args:
        path (Path or list of such): path(s) to file(s).
        key (str): identifier to address the data in the vtu file.
        shape (tuple of int): shape of target 2d pixelated array, in matrix indexing.
            series (bool): flag controlling whether a time series of images
                is created.

    Returns:
        darsia.Image: scalar image (space-time if list provided)

    """
    if isinstance(path, Path):
        # Read from file
        data, meta = _read_single_vtu_image(path, key, shape, **kwargs)

        # Update metadata
        meta["series"] = False

    elif isinstance(path, list):
        # Read from file
        data_collection = [
            _read_single_vtu_image(p, key, shape, **kwargs) for p in path
        ]

        # Create a space-time optical image through stacking along the time axis
        meta = data_collection[0][1]  # NOTE: No safety check
        dim = meta["space_dim"]
        data = np.stack([d[0] for d in data_collection], axis=dim)

        # Fix metadata
        meta["series"] = True

    meta["time"] = kwargs.get("time", None)

    # Define image
    return darsia.ScalarImage(data, **meta)


def _read_single_vtu_image(
    path: Path, key: str, shape: tuple[int], **kwargs
) -> tuple[np.ndarray, dict]:
    """Utility function for setting up a single vtu image.

    Args:
        path (Path): path to single vtu file.
        key (str): key to address data.
        shape (tuple of int): shape of target 2d pixelated array, in matrix indexing.
            series (bool): flag controlling whether a time series of images
                is created.

    Returns:
        np.ndarray: data array
        dict: meta

    Raises:
        ImportError: if meshio is not installed
        NotImplementedError: if 3d VTU image is provided.

    """
    try:
        import meshio
    except ImportError:
        raise ImportError("meshio not available on this system")

    # VTU data comes in 3d. The user-input voxel_size implicitly informs on the
    # true ambient dimension.
    dim = len(shape)
    if dim != 2:
        raise NotImplementedError

    # Fix indexing: aim for matrix indexing in the target image
    indexing = "ijk"[:dim]

    # At the same time, the vtu image may represent a lower-dimensional object
    # in ambient dimensional space (of dimension dim).
    vtu_dim = kwargs.get("vtu_dim", dim)

    # Fetch vtu data
    vtu_data = meshio.read(path)

    # Fetch grid information and data as array
    points = vtu_data.points[:, :dim]
    cells = vtu_data.cells[0].data
    data = vtu_data.cell_data[key][0]

    # Fetch origin from points - take into account orientation of axes
    cartesian_origin = np.array([np.min(points[:, i]) for i in range(dim)])
    cartesian_opposite = np.array([np.max(points[:, i]) for i in range(dim)])
    origin = []
    for i, axis in enumerate("xyz"[:dim]):
        _, revert = darsia.interpret_indexing(axis, indexing)
        origin.append(cartesian_opposite[i] if revert else cartesian_origin[i])

    # Fetch dimensions from points - need to reshuffle to matrix indexing
    cartesian_dimensions = [
        np.max(points[:, i]) - np.min(points[:, i]) for i in range(dim)
    ]
    dimensions = [
        cartesian_dimensions[darsia.interpret_indexing(axis, indexing)[0]]
        for axis in "xyz"[:dim]
    ]

    # Collect all metadata
    meta = {
        "space_dim": dim,
        "indexing": indexing,
        "dimensions": dimensions,
        "origin": origin,
    }

    # Create actual pixelated data
    if dim == vtu_dim:
        data = _resample_data(data, points, cells, shape, meta)
    elif vtu_dim < dim:
        width = kwargs.get("width")  # effective width of lower-dimension object
        data, updated_dimensions, updated_origin = _embed_data(
            data, points, cells, shape, meta, width
        )
        meta["dimensions"] = updated_dimensions
        meta["origin"] = updated_origin

    return data, meta


def _resample_data(
    data: np.ndarray,
    points: np.ndarray,
    cells: np.ndarray,
    shape: tuple[int],
    meta: dict,
) -> np.ndarray:
    """Sampling of data on arbitrary mesh to regular voxel grids (in 2d and 3d).

    Args:
        data (array): data array.
        points (array): coordinates of triangulation.
        cells (array): connectivity of triangulation.
        shape (tuple of int): size of the target quad mesh in matrix indexing.
        meta (dict): meta data dictionary associated to image.

    """
    # Fetch meta data
    dim = meta["space_dim"]
    indexing = meta["indexing"]

    # Problem size
    num_cells, num_points_per_cell = cells.shape
    num_points, _ = points.shape

    # Corners of each cell
    corners = [points[cells[:, i]] for i in range(num_points_per_cell)]

    # Centroid as average of corners
    centroids = sum(corners) / num_points_per_cell

    # Find associated Cartesian voxel to each centroid
    cartesian_origin = np.array([np.min(points[:, i]) for i in range(dim)])
    cartesian_dimensions = np.array(
        [np.max(points[:, i]) - np.min(points[:, i]) for i in range(dim)]
    )
    cart_ind = np.array(
        [darsia.interpret_indexing(axis, indexing)[0] for axis in "xyz"[:dim]]
    )
    cartesian_shape = np.array(shape)[cart_ind]
    cartesian_voxels = np.floor(
        np.multiply(
            np.divide(
                centroids - np.outer(np.ones(num_cells), cartesian_origin),
                np.outer(np.ones(num_cells), cartesian_dimensions),
            ),
            np.outer(np.ones(num_cells), cartesian_shape),
        )
    ).astype(int)

    # Translate between Cartesian and matrix indexing.
    # Requires two operations: reshuffling axes, reoirenting axis.
    voxels = np.zeros_like(cartesian_voxels, dtype=int)
    for i, index in enumerate(indexing):
        cartesian_index, revert = darsia.interpret_indexing(index, "xyz"[:dim])
        voxels[:, i] = (
            shape[i] - 1 - cartesian_voxels[:, cartesian_index]
            if revert
            else cartesian_voxels[:, cartesian_index]
        )

    # Associate cell data to voxel data
    pixelated_data = np.zeros(shape, dtype=data.dtype)
    voxels_indexing = tuple(voxels[:, j] for j in range(dim))
    pixelated_data[voxels_indexing] += data

    # Fill-in values if required.
    fill_in = np.ones(shape, dtype=bool)
    fill_in[voxels_indexing] = False
    have_value = np.logical_not(fill_in)
    if np.any(fill_in):
        # Interpolate for all pixels
        pixels = np.nonzero(have_value)
        pixel_data = pixelated_data[pixels]
        interpolator = NearestNDInterpolator(
            np.transpose(np.vstack(pixels)), pixel_data
        )

        # Define mesh as input for interpolation
        Ny, Nx = shape
        x = np.arange(Nx)
        y = np.arange(Ny)
        X_pixel, Y_pixel = np.meshgrid(x, y)
        full_pixel_vector = np.transpose(
            np.vstack((np.ravel(Y_pixel), np.ravel(X_pixel)))
        )

        # Evaluate interpolation
        full_data_vector = interpolator(full_pixel_vector)
        full_data = full_data_vector.reshape(shape)

        # Assign to pixelated data
        pixelated_data = full_data

    return pixelated_data


def _embed_data(
    data: np.ndarray,
    points: np.ndarray,
    cells: np.ndarray,
    shape: tuple[int],
    meta: dict,
    width: float,
    conservative: bool = True,
    resolution: int = 10,
    tol: float = None,
    #    dimensions,
    #    roi=None,
) -> tuple[np.ndarray, list[float], list[float]]:
    """
    Auxiliary routine to embed lower dimensional data into ambient
    dimension. Use sampling in normal direction.

    NOTE: 1. Only implemented for 1d to 2d.

    NOTE: 2. A quite crude approximation is made, essentially making each
        voxel, which is sufficiently close, a fully equivalent representation
        of the lower dimensional object. One can imagine, that a weighted
        interpolation approach is more accurate. TODO.

    Args:
        data (array): data array.
        points (array): coordinates of triangulation.
        cells (array): connectivity of triangulation.
        shape (tuple of int): size of the target quad mesh in matrix indexing.
        meta (dict): meta data dictionary associated to image.
        width (float): width of the lower dimensional object.

    Returns:
        np.ndarray: embedded data array complying with embedded space.
        list of float: dimenions of embedded data (Cartesian indexing)
        list of float: Cartesian coordinates of the voxel origin of the embedded data.

    Raises:
        NotImplementedError: if ambient dimension is not 2d.

    """
    # Fetch meta data
    dim = meta["space_dim"]
    if dim != 2:
        raise NotImplementedError
    indexing = meta["indexing"]

    # Problem size
    num_cells, num_points_per_cell = cells.shape
    num_points, _ = points.shape

    # Corners of each cell
    corners = [points[cells[:, i]] for i in range(num_points_per_cell)]

    # Centroid as average of corners
    centroids = sum(corners) / num_points_per_cell

    # Normals to each centroid - only works for 1d in 2d images
    tangentials = points[cells[:, 1]] - points[cells[:, 0]]
    rotation = np.array([[0, -1], [1, 0]], dtype=float)
    normals = np.transpose(rotation.dot(np.transpose(tangentials)))
    normals_length = np.linalg.norm(normals, axis=1)
    unit_normals = np.diag(1.0 / normals_length).dot(normals)

    # Provide a point cloud effectively lying on the higher-dimensional
    # representation of the lower-dimensional object.
    points_lower = np.vstack(
        tuple(
            points[cells[:, i]] - 0.5 * width * unit_normals
            for i in range(num_points_per_cell)
        )
    )
    points_upper = np.vstack(
        tuple(
            points[cells[:, i]] + 0.5 * width * unit_normals
            for i in range(num_points_per_cell)
        )
    )
    extruded_points = np.vstack((points, points_lower, points_upper))

    # Determine origin and dimensions of the point cloud - all in Cartesian indexing.
    cartesian_origin = np.min(extruded_points, axis=0)
    cartesian_dimensions = np.array(
        [
            np.max(extruded_points[:, i]) - np.min(extruded_points[:, i])
            for i in range(dim)
        ]
    )
    cart_ind = np.array(
        [darsia.interpret_indexing(axis, indexing)[0] for axis in "xyz"[:dim]]
    )
    cartesian_shape = np.array(shape)[cart_ind]
    voxel_origin = [np.min(extruded_points[:, 0]), np.max(extruded_points[:, 1])]

    # Sample the centroids in normal and tangential direction,
    # according to the effective width, size and correpsonding
    # resolution of the target image. This necessary to provide
    # continuous data without holes.
    cartesian_voxel_size = cartesian_dimensions / cartesian_shape
    min_voxel_size = np.min(cartesian_voxel_size)

    # In normal direction.
    normal_resolution = np.ceil(width / min_voxel_size).astype(int)
    extruded_centroids = centroids.copy()
    extruded_data = data.copy()
    extruded_tangentials = tangentials.copy()
    for i in range(normal_resolution):
        fraction = 0.5 * width * i / normal_resolution
        centroids_lower = centroids - fraction * unit_normals
        centroids_upper = centroids + fraction * unit_normals
        extruded_centroids = np.vstack(
            (extruded_centroids, centroids_lower, centroids_upper)
        )
        extruded_data = np.hstack((extruded_data, data, data))
        extruded_tangentials = np.vstack(
            (extruded_tangentials, tangentials, tangentials)
        )

    normally_extruded_centroids = extruded_centroids.copy()
    normally_extruded_data = extruded_data.copy()

    # In tangential direction.
    tangential_resolution = np.ceil(np.max(normals_length / min_voxel_size)).astype(int)
    for i in range(tangential_resolution):
        fraction = 0.5 * (i + 1) / tangential_resolution
        extruded_centroids_along_tangential_lower = (
            normally_extruded_centroids - fraction * extruded_tangentials
        )
        extruded_centroids_along_tangential_upper = (
            normally_extruded_centroids + fraction * extruded_tangentials
        )
        extruded_centroids = np.vstack(
            (
                extruded_centroids,
                extruded_centroids_along_tangential_lower,
                extruded_centroids_along_tangential_upper,
            )
        )
        extruded_data = np.hstack(
            (extruded_data, normally_extruded_data, normally_extruded_data)
        )

    num_extruded_centroids = extruded_centroids.shape[0]

    # Determine the corresponding Cartesian voxels of the extruded centroids.
    cartesian_voxels = np.floor(
        np.multiply(
            np.divide(
                extruded_centroids
                - np.outer(np.ones(num_extruded_centroids), cartesian_origin),
                np.outer(np.ones(num_extruded_centroids), cartesian_dimensions),
            ),
            np.outer(np.ones(num_extruded_centroids), cartesian_shape),
        )
    ).astype(int)

    # Translate between Cartesian and matrix indexing.
    # Requires two operations: reshuffling axes, reoirenting axis.
    voxels = np.zeros_like(cartesian_voxels, dtype=int)
    for i, index in enumerate(indexing):
        cartesian_index, revert = darsia.interpret_indexing(index, "xyz"[:dim])
        voxels[:, i] = (
            shape[i] - 1 - cartesian_voxels[:, cartesian_index]
            if revert
            else cartesian_voxels[:, cartesian_index]
        )

    # Allocate space for embedded data - use matrix indexing
    # Associate cell data to voxel data
    embedded_data = np.zeros(shape, dtype=data.dtype)
    voxels_indexing = tuple(voxels[:, j] for j in range(dim))
    embedded_data[voxels_indexing] += extruded_data

    # If the option 'conservative' is chosen, rescale the image such that the
    # volumetric integrals are identical.
    if conservative:
        # Integrate input data
        extruded_cell_volumes = np.linalg.norm(normals, axis=1) * width
        integrated_data = np.sum(np.multiply(data, extruded_cell_volumes))

        # Integrated reconstructed data
        voxel_volume = np.prod(cartesian_voxel_size)
        integrated_embedded_data = np.sum(embedded_data) * voxel_volume

        # Rescale
        embedded_data *= integrated_data / integrated_embedded_data

    # Due to the effective widening of the lower-dimensional object,
    # the dimensions have possibly changed.
    to_matrix_indexing = [
        darsia.interpret_indexing("ijk"[i], "xyz"[:dim])[0] for i in range(dim)
    ]
    dimensions = [cartesian_dimensions[i] for i in to_matrix_indexing]

    return embedded_data, dimensions, voxel_origin

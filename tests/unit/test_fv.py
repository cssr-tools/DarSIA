"""Unit tests for finite volume utilities."""

import numpy as np

import darsia


def test_divergence_2d():
    # Create divergence matrix
    grid = darsia.Grid(shape=(4, 5), voxel_size=[0.5, 0.25])
    divergence = darsia.FVDivergence(grid).mat.todense()

    # Check shape
    assert np.allclose(divergence.shape, (grid.num_cells, grid.num_faces))

    # Check values in corner cells
    assert np.allclose(np.nonzero(divergence[0])[1], [0, 15])
    assert np.allclose(divergence[0, np.array([0, 15])], [0.25, 0.5])

    assert np.allclose(np.nonzero(divergence[4])[1], [3, 15, 19])
    assert np.allclose(divergence[4, np.array([3, 15, 19])], [0.25, -0.5, 0.5])

    assert np.allclose(np.nonzero(divergence[16])[1], [12, 27])
    assert np.allclose(divergence[16, np.array([12, 27])], [0.25, -0.5])

    assert np.allclose(np.nonzero(divergence[19])[1], [14, 30])
    assert np.allclose(divergence[19, np.array([14, 30])], [-0.25, -0.5])

    # Check value for interior cell
    assert np.allclose(np.nonzero(divergence[6])[1], [4, 5, 17, 21])
    assert np.allclose(
        divergence[6, np.array([4, 5, 17, 21])], [-0.25, 0.25, -0.5, 0.5]
    )


def test_divergence_3d():
    # Create divergence matrix
    grid = darsia.Grid(shape=(3, 4, 5), voxel_size=[0.5, 0.25, 2])
    divergence = darsia.FVDivergence(grid).mat.todense()

    # Check shape
    assert np.allclose(divergence.shape, (grid.num_cells, grid.num_faces))

    # Check values in corner cells
    assert np.allclose(np.nonzero(divergence[0])[1], [0, 40, 85])
    assert np.allclose(divergence[0, np.array([0, 40, 85])], [0.5, 1, 0.125])

    assert np.allclose(np.nonzero(divergence[11])[1], [7, 48, 96])
    assert np.allclose(divergence[11, np.array([7, 48, 96])], [-0.5, -1, 0.125])

    assert np.allclose(np.nonzero(divergence[59])[1], [39, 84, 132])
    assert np.allclose(divergence[59, np.array([39, 84, 132])], [-0.5, -1, -0.125])

    # Check value for interior cell
    assert np.allclose(np.nonzero(divergence[16])[1], [10, 11, 50, 53, 89, 101])
    assert np.allclose(
        divergence[16, np.array([10, 11, 50, 53, 89, 101])],
        [-0.5, 0.5, -1, 1, -0.125, 0.125],
    )


def test_mass_2d():
    grid = darsia.Grid(shape=(4, 5), voxel_size=[0.5, 0.25])
    mass = darsia.FVMass(grid).mat.todense()

    # Check shape
    assert np.allclose(mass.shape, (grid.num_cells, grid.num_cells))

    # Check diagonal structure
    assert np.linalg.norm(mass - np.diag(np.diag(mass))) < 1e-10

    # Check diagonal values
    assert len(np.unique(np.diag(mass))) == 1
    assert np.isclose(mass[0, 0], 0.125)


def test_mass_3d():
    grid = darsia.Grid(shape=(3, 4, 5), voxel_size=[0.5, 0.25, 2])
    mass = darsia.FVMass(grid).mat.todense()

    # Check shape
    assert np.allclose(mass.shape, (grid.num_cells, grid.num_cells))

    # Check diagonal structure
    assert np.linalg.norm(mass - np.diag(np.diag(mass))) < 1e-10

    # Check diagonal values
    assert len(np.unique(np.diag(mass))) == 1
    assert np.isclose(mass[0, 0], 0.25)


def test_mass_face_2d():
    grid = darsia.Grid(shape=(4, 5), voxel_size=[0.5, 0.25])
    mass = darsia.FVMass(grid, mode="faces", lumping=True).mat.todense()

    # Check shape
    assert np.allclose(mass.shape, (grid.num_faces, grid.num_faces))

    # Check diagonal structure
    assert np.linalg.norm(mass - np.diag(np.diag(mass))) < 1e-10

    # Check diagonal values
    assert len(np.unique(np.diag(mass))) == 1
    assert all([np.isclose(mass[i, i], 0.5 * 0.25) for i in range(20)])


def test_mass_face_3d():
    grid = darsia.Grid(shape=(3, 4, 5), voxel_size=[0.5, 0.25, 2])
    mass = darsia.FVMass(grid, mode="faces", lumping=True).mat.todense()

    # Check shape
    assert np.allclose(mass.shape, (grid.num_faces, grid.num_faces))

    # Check diagonal structure
    assert np.linalg.norm(mass - np.diag(np.diag(mass))) < 1e-10

    # Check diagonal values
    assert len(np.unique(np.diag(mass))) == 1
    assert all([np.isclose(mass[i, i], 0.5 * 0.25 * 2) for i in range(60)])


def test_tangential_reconstruction_2d_1():
    grid = darsia.Grid(shape=(2, 3), voxel_size=[0.5, 0.25])
    tangential_reconstruction = (
        darsia.FVTangentialFaceReconstruction(grid).mat[0].todense()
    )

    # Check shape
    assert np.allclose(
        tangential_reconstruction.shape, (grid.num_faces, grid.num_faces)
    )

    # Check values - first for exterior faces
    assert np.allclose(tangential_reconstruction[0], [0, 0, 0, 0.25, 0.25, 0, 0])
    assert np.allclose(tangential_reconstruction[4], [0.25, 0.25, 0, 0, 0, 0, 0])

    # Check values - then for interior faces
    assert np.allclose(tangential_reconstruction[1], [0, 0, 0, 0.25, 0.25, 0.25, 0.25])


def test_tangential_reconstruction_2d_2():
    grid = darsia.Grid(shape=(3, 4), voxel_size=[0.5, 0.25])
    tangential_reconstruction_dense = (
        darsia.FVTangentialFaceReconstruction(grid).mat[0].todense()
    )

    # Check shape
    assert np.allclose(
        tangential_reconstruction_dense.shape, (grid.num_faces, grid.num_faces)
    )

    # Check values - first for exterior faces
    assert np.allclose(np.nonzero(tangential_reconstruction_dense[0])[1], [8, 9])
    assert np.allclose(np.nonzero(tangential_reconstruction_dense[7])[1], [15, 16])

    # Check values - then for interior faces
    assert np.allclose(
        np.nonzero(tangential_reconstruction_dense[2])[1], [8, 9, 11, 12]
    )
    assert np.allclose(np.nonzero(tangential_reconstruction_dense[15])[1], [4, 5, 6, 7])

    # Apply once and prove values
    tangential_reconstruction = darsia.FVTangentialFaceReconstruction(grid)
    normal_flux = np.arange(grid.num_faces)
    tangential_flux = tangential_reconstruction(normal_flux)
    assert np.allclose(
        tangential_flux[np.array([0, 1, 4, 8, 12, 16])], [4.25, 4.75, 13, 0.5, 3.5, 3]
    )


def test_full_reconstruction_2d_2():
    grid = darsia.Grid(shape=(3, 4), voxel_size=[0.5, 0.25])

    # Apply once and prove values
    tangential_reconstruction = darsia.FVFullFaceReconstruction(grid)
    normal_flux = np.arange(grid.num_faces)
    full_flux = tangential_reconstruction(normal_flux)

    # Check shape
    assert np.allclose(full_flux.shape, (grid.num_faces, 2))

    # Check values
    assert np.allclose(full_flux[0], [0, 4.25])
    assert np.allclose(full_flux[1], [1, 4.75])
    assert np.allclose(full_flux[4], [4, 13])
    assert np.allclose(full_flux[8], [0.5, 8])
    assert np.allclose(full_flux[12], [3.5, 12])
    assert np.allclose(full_flux[16], [3, 16])


def test_tangential_reconstruction_3d():
    grid = darsia.Grid(shape=(3, 3, 3), voxel_size=[0.5, 0.25, 2])
    tangential_reconstruction = darsia.FVTangentialFaceReconstruction(grid)

    # Apply once and probe values
    normal_flux = np.arange(grid.num_faces)
    tangential_flux = tangential_reconstruction(normal_flux, concatenate=False)

    # Corner block
    assert np.allclose(
        [tangential_flux[0][0], tangential_flux[1][0]], [(18 + 19) / 4, (36 + 37) / 4]
    )
    assert np.allclose(
        [tangential_flux[0][18], tangential_flux[1][18]], [(0 + 2) / 4, (36 + 39) / 4]
    )
    assert np.allclose(
        [tangential_flux[0][36], tangential_flux[1][36]], [(0 + 6) / 4, (18 + 24) / 4]
    )

    # Center block
    assert np.allclose(
        [tangential_flux[0][8], tangential_flux[1][8]],
        [(24 + 25 + 27 + 28) / 4, (39 + 40 + 48 + 49) / 4],
    )
    assert np.allclose(
        [tangential_flux[0][25], tangential_flux[1][25]],
        [(6 + 7 + 8 + 9) / 4, (37 + 40 + 46 + 49) / 4],
    )
    assert np.allclose(
        [tangential_flux[0][40], tangential_flux[1][40]],
        [(2 + 3 + 8 + 9) / 4, (19 + 22 + 25 + 28) / 4],
    )


def test_full_reconstruction_3d():
    grid = darsia.Grid(shape=(3, 3, 3), voxel_size=[0.5, 0.25, 2])
    full_reconstuction = darsia.FVFullFaceReconstruction(grid)

    # Apply once and probe values
    normal_flux = np.arange(grid.num_faces)
    full_flux = full_reconstuction(normal_flux)

    # Corner block
    assert np.allclose(full_flux[0], [0, (18 + 19) / 4, (36 + 37) / 4])
    assert np.allclose(full_flux[18], [(0 + 2) / 4, 18, (36 + 39) / 4])
    assert np.allclose(full_flux[36], [(0 + 6) / 4, (18 + 24) / 4, 36])

    # Center block
    assert np.allclose(
        full_flux[8], [8, (24 + 25 + 27 + 28) / 4, (39 + 40 + 48 + 49) / 4]
    )
    assert np.allclose(
        full_flux[25], [(6 + 7 + 8 + 9) / 4, 25, (37 + 40 + 46 + 49) / 4]
    )
    assert np.allclose(
        full_flux[40], [(2 + 3 + 8 + 9) / 4, (19 + 22 + 25 + 28) / 4, 40]
    )


def test_face_to_cell_2d():
    grid = darsia.Grid(shape=(3, 4), voxel_size=[0.5, 0.25])
    num_faces = grid.num_faces
    flat_flux = np.arange(num_faces)
    cell_flux = darsia.face_to_cell(grid, flat_flux)

    # Check shape
    assert np.allclose(cell_flux.shape, (*grid.shape, grid.dim))

    # Check values
    print(cell_flux)
    assert np.allclose(cell_flux[0, 0], [0, 4])
    assert np.allclose(cell_flux[2, 3], [3.5, 8])
    assert np.allclose(cell_flux[1, 1], [2.5, 10.5])


def test_face_to_cell_3d():
    grid = darsia.Grid(shape=(3, 4, 5), voxel_size=[0.5, 0.25, 2])
    num_faces = grid.num_faces
    flat_flux = np.arange(num_faces)
    cell_flux = darsia.face_to_cell(grid, flat_flux)

    # Check shape
    assert np.allclose(cell_flux.shape, (*grid.shape, grid.dim))

    # Check values
    assert np.allclose(cell_flux[0, 0, 0], [0, 20, 42.5])
    assert np.allclose(cell_flux[2, 3, 4], [19.5, 42, 66])
    assert np.allclose(cell_flux[1, 1, 1], [10.5, 51.5, 95])

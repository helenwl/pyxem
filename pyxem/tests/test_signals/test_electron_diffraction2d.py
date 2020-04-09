# -*- coding: utf-8 -*-
# Copyright 2017-2020 The pyXem developers
#
# This file is part of pyXem.
#
# pyXem is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyXem is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyXem.  If not, see <http://www.gnu.org/licenses/>.

import pytest
import numpy as np
import dask.array as da
import hyperspy.api as hs

from hyperspy.signals import Signal1D, Signal2D

from pyxem.signals.electron_diffraction2d import ElectronDiffraction2D
from pyxem.signals.electron_diffraction2d import LazyElectronDiffraction2D


def test_init():
    z = np.zeros((2, 2, 2, 2))
    dp = ElectronDiffraction2D(
        z, metadata={"Acquisition_instrument": {"SEM": "Expensive-SEM"}}
    )


class TestSimpleMaps:
    # Confirms that maps run without error.

    def test_center_direct_beam_cross_correlate(self, diffraction_pattern):
        assert isinstance(diffraction_pattern, ElectronDiffraction2D)
        diffraction_pattern.center_direct_beam(
            method="cross_correlate", radius_start=1, radius_finish=3
        )
        assert isinstance(diffraction_pattern, ElectronDiffraction2D)

    def test_center_direct_beam_xc_return_shifts(self, diffraction_pattern):
        shifts = diffraction_pattern.center_direct_beam(
            method="cross_correlate",
            radius_start=1,
            radius_finish=3,
            return_shifts=True,
        )
        ans = np.array([[-0.45, -0.45], [0.57, 0.57], [-0.45, -0.45], [0.52, 0.52]])
        np.testing.assert_almost_equal(shifts, ans)

    def test_center_direct_beam_blur_return_shifts(self, diffraction_pattern):
        shifts = diffraction_pattern.center_direct_beam(
            method="blur", sigma=5, half_square_width=3, return_shifts=True
        )
        ans = np.array([[-1.0, -1.0], [-0.0, -0.0], [-1.0, -1.0], [-0.0, -0.0]])
        np.testing.assert_almost_equal(shifts, ans)

    def test_center_direct_beam_in_small_region(self, diffraction_pattern):
        assert isinstance(diffraction_pattern, ElectronDiffraction2D)
        diffraction_pattern.center_direct_beam(
            method="blur", sigma=int(5), half_square_width=3
        )
        assert isinstance(diffraction_pattern, ElectronDiffraction2D)

    def test_apply_affine_transformation(self, diffraction_pattern):
        diffraction_pattern.apply_affine_transformation(
            D=np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        )
        assert isinstance(diffraction_pattern, ElectronDiffraction2D)

    def test_apply_affine_transforms_paths(self, diffraction_pattern):
        D = np.array([[1.0, 0.9, 0.0], [1.1, 1.0, 0.0], [0.0, 0.0, 1.0]])
        s = Signal2D(np.asarray([[D, D], [D, D]]))
        static = diffraction_pattern.apply_affine_transformation(D, inplace=False)
        dynamic = diffraction_pattern.apply_affine_transformation(s, inplace=False)
        assert np.allclose(static.data, dynamic.data, atol=1e-3)

    def test_apply_affine_transformation_with_casting(self, diffraction_pattern):
        diffraction_pattern.change_dtype("uint8")
        transformed_dp = ElectronDiffraction2D(
            diffraction_pattern
        ).apply_affine_transformation(
            D=np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.2]]),
            order=2,
            keep_dtype=True,
            inplace=False,
        )
        assert transformed_dp.data.dtype == "uint8"

    methods = ["average", "nan"]

    @pytest.mark.parametrize("method", methods)
    def test_remove_dead_pixels(self, diffraction_pattern, method):
        dpr = diffraction_pattern.remove_deadpixels(
            [[1, 2], [5, 6]], method, inplace=False
        )
        assert isinstance(dpr, ElectronDiffraction2D)


class TestSimpleHyperspy:
    # Tests functions that assign to hyperspy metadata

    def test_set_experimental_parameters(self, diffraction_pattern):
        diffraction_pattern.set_experimental_parameters(
            beam_energy=3.0,
            camera_length=3.0,
            scan_rotation=1.0,
            convergence_angle=1.0,
            rocking_angle=1.0,
            rocking_frequency=1.0,
            exposure_time=1.0,
        )
        assert isinstance(diffraction_pattern, ElectronDiffraction2D)

    def test_set_scan_calibration(self, diffraction_pattern):
        diffraction_pattern.set_scan_calibration(19)
        assert isinstance(diffraction_pattern, ElectronDiffraction2D)

    @pytest.mark.parametrize(
        "calibration, center", [(1, (4, 4),), (0.017, (3, 3)), (0.5, None,),]
    )
    def test_set_diffraction_calibration(
        self, diffraction_pattern, calibration, center
    ):
        calibrated_center = (
            calibration * np.array(center) if center is not None else center
        )
        diffraction_pattern.set_diffraction_calibration(
            calibration, center=calibrated_center
        )
        dx, dy = diffraction_pattern.axes_manager.signal_axes
        assert dx.scale == calibration and dy.scale == calibration
        if center is not None:
            assert np.all(
                diffraction_pattern.isig[0.0, 0.0].data
                == diffraction_pattern.isig[center[0], center[1]].data
            )


class TestGainNormalisation:
    @pytest.mark.parametrize(
        "dark_reference, bright_reference", [(-1, 1), (0, 1), (0, 256),]
    )
    def test_apply_gain_normalisation(
        self, diffraction_pattern, dark_reference, bright_reference
    ):
        dpr = diffraction_pattern.apply_gain_normalisation(
            dark_reference=dark_reference,
            bright_reference=bright_reference,
            inplace=False,
        )
        assert dpr.max() == bright_reference
        assert dpr.min() == dark_reference


class TestDirectBeamMethods:
    @pytest.mark.parametrize(
        "mask_expected",
        [
            (
                np.array(
                    [
                        [False, False, False, False, False, False, False, False],
                        [False, False, False, False, False, False, False, False],
                        [False, False, False, True, True, False, False, False],
                        [False, False, True, True, True, True, False, False],
                        [False, False, True, True, True, True, False, False],
                        [False, False, False, True, True, False, False, False],
                        [False, False, False, False, False, False, False, False],
                        [False, False, False, False, False, False, False, False],
                    ]
                ),
            ),
        ],
    )
    def test_get_direct_beam_mask(self, diffraction_pattern, mask_expected):
        mask_calculated = diffraction_pattern.get_direct_beam_mask(2)
        assert isinstance(mask_calculated, Signal2D)
        assert np.equal(mask_calculated, mask_expected)


class TestBackgroundMethods:
    @pytest.mark.parametrize(
        "method, kwargs",
        [
            ("h-dome", {"h": 1,}),
            ("gaussian_difference", {"sigma_min": 0.5, "sigma_max": 1,}),
            ("median", {"footprint": 4,}),
            ("reference_pattern", {"bg": np.ones((8, 8)),}),
        ],
    )
    def test_remove_background(self, diffraction_pattern, method, kwargs):
        bgr = diffraction_pattern.remove_background(method=method, **kwargs)
        assert bgr.data.shape == diffraction_pattern.data.shape
        assert bgr.max() <= diffraction_pattern.max()

    @pytest.mark.xfail(raises=TypeError)
    def test_no_kwarg(self, diffraction_pattern):
        bgr = diffraction_pattern.remove_background(method="h-dome")


class TestPeakFinding:
    # This is assertion free testing

    @pytest.fixture
    def ragged_peak(self):
        """
        A small selection of peaks in an ElectronDiffraction2D, to allow
        flexibilty of test building here.
        """
        pattern = np.zeros((2, 2, 128, 128))
        pattern[:, :, 40:42, 45] = 1
        pattern[:, :, 110, 30:32] = 1
        pattern[1, 0, 71:73, 21:23] = 1
        dp = ElectronDiffraction2D(pattern)
        dp.set_diffraction_calibration(1)
        return dp

    methods = [
        "zaefferer",
        "laplacian_of_gaussians",
        "difference_of_gaussians",
        "stat",
        "xc",
    ]

    @pytest.mark.parametrize("method", methods)
    # skimage internals
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_findpeaks_ragged(self, ragged_peak, method):
        if method == "xc":
            disc = np.ones((2, 2))
            output = ragged_peak.find_peaks(
                method="xc", disc_image=disc, min_distance=3
            )
        else:
            output = ragged_peak.find_peaks(method=method, show_progressbar=False)


class TestsAssertionless:
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    # we don't want to use xc in this bit
    @pytest.mark.filterwarnings("ignore::UserWarning")
    def test_find_peaks_interactive(self, diffraction_pattern):
        from matplotlib import pyplot as plt

        plt.ion()  # to make plotting non-blocking
        diffraction_pattern.find_peaks_interactive()
        plt.close("all")


@pytest.mark.xfail(raises=NotImplementedError)
class TestNotImplemented:
    def test_failing_run(self, diffraction_pattern):
        diffraction_pattern.find_peaks(method="no_such_method_exists")

    def test_remove_dead_pixels_failing(self, diffraction_pattern):
        dpr = diffraction_pattern.remove_deadpixels(
            [[1, 2], [5, 6]], "fake_method", inplace=False, progress_bar=False
        )

    def test_remove_background_fake_method(self, diffraction_pattern):
        bgr = diffraction_pattern.remove_background(method="fake_method")


class TestComputeAndAsLazyElectron2D:
    def test_2d_data_compute(self):
        dask_array = da.random.random((100, 150), chunks=(50, 50))
        s = LazyElectronDiffraction2D(dask_array)
        scale0, scale1, metadata_string = 0.5, 1.5, "test"
        s.axes_manager[0].scale = scale0
        s.axes_manager[1].scale = scale1
        s.metadata.Test = metadata_string
        s.compute()
        assert isinstance(s, ElectronDiffraction2D)
        assert not hasattr(s.data, "compute")
        assert s.axes_manager[0].scale == scale0
        assert s.axes_manager[1].scale == scale1
        assert s.metadata.Test == metadata_string
        assert dask_array.shape == s.data.shape

    def test_4d_data_compute(self):
        dask_array = da.random.random((4, 4, 10, 15), chunks=(1, 1, 10, 15))
        s = LazyElectronDiffraction2D(dask_array)
        s.compute()
        assert s.__class__ == ElectronDiffraction2D
        assert dask_array.shape == s.data.shape

    def test_2d_data_as_lazy(self):
        data = np.random.random((100, 150))
        s = ElectronDiffraction2D(data)
        scale0, scale1, metadata_string = 0.5, 1.5, "test"
        s.axes_manager[0].scale = scale0
        s.axes_manager[1].scale = scale1
        s.metadata.Test = metadata_string
        s_lazy = s.as_lazy()
        assert isinstance(s_lazy, LazyElectronDiffraction2D)
        assert hasattr(s_lazy.data, "compute")
        assert s_lazy.axes_manager[0].scale == scale0
        assert s_lazy.axes_manager[1].scale == scale1
        assert s_lazy.metadata.Test == metadata_string
        assert data.shape == s_lazy.data.shape

    def test_4d_data_as_lazy(self):
        data = np.random.random((4, 10, 15))
        s = ElectronDiffraction2D(data)
        s_lazy = s.as_lazy()
        assert isinstance(s_lazy, LazyElectronDiffraction2D)
        assert data.shape == s_lazy.data.shape


class TestDecomposition:
    def test_decomposition_class_assignment(self, diffraction_pattern):
        diffraction_pattern.decomposition()
        assert isinstance(diffraction_pattern, ElectronDiffraction2D)

class TestAffineTransformation:
    @pytest.fixture
    def ones(self):
        ones_diff = ElectronDiffraction2D(data=np.ones(shape=(5, 5)))
        ones_diff.diffraction_calibration = 0.1
        ones_diff.beam_energy = 200
        ones_diff.axes_manager.signal_axes[0].name = "kx"
        ones_diff.axes_manager.signal_axes[1].name = "ky"
        ones_diff.unit = "k_nm^-1"
        return ones_diff

    def test_1d_azimuthal_integration(self, ones):
        integration = ones.get_azimuthal_integral1d(npt_rad=10)
        print(integration)
    def test_2d_azimuthal_integration(self, ones):
        integration = ones.get_azimuthal_integral2d(npt_rad=10)
        print(integration)


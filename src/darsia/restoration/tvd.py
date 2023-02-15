"""
Module wrapping TV denoising algoriths from skimage
into the realm of DarSIA, operating on darsia.Image.

"""

import numpy as np
import skimage


class TVD:
    """
    Total variation denoising through skimage.restoration.

    """

    def __init__(self, key: str = "", **kwargs) -> None:
        """
        Constructor.

        Args:
            key (str): Prefix for kwargs arguments.

        """
        self.method = kwargs.get(key + "smoothing method", "chambolle")
        self.weight = kwargs.get(key + "smoothing weight", 0.1)
        self.eps = kwargs.get(key + "smoothing eps", 2e-4)
        self.max_num_iter = kwargs.get(key + "smoothing max_num_iter", 200)

    def __call__(self, img: np.ndarray) -> np.ndarray:
        """
        Application of anisotropic resizing and tv denoising.

        Args:
            img (np.ndarray): image

        Returns:
            np.ndarray: upscaled image

        """

        # Apply TVD
        if self.method == "chambolle":
            img = skimage.restoration.denoise_tv_chambolle(
                img,
                weight=self.weight,
                eps=self.eps,
                max_num_iter=self.max_num_iter,
            )

        elif self.method == "anisotropic bregman":
            img = skimage.restoration.denoise_tv_bregman(
                img,
                weight=self.weight,
                eps=self.eps,
                max_num_iter=self.max_num_iter,
                isotropic=False,
            )

        elif self.method == "isotropic bregman":
            img = skimage.restoration.denoise_tv_bregman(
                img,
                weight=self.weight,
                eps=self.eps,
                max_num_iter=self.max_num_iter,
                isotropic=True,
            )

        else:
            raise ValueError(f"Method {self.method} not supported.")

        return img

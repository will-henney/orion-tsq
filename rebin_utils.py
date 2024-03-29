import numpy as np


def downsample(images, mask, weights=None, verbose=False, mingood=1):
    """
    Resample (average) a list of 2d images at 2x2, taking account of a logical mask

    Now optionally use a weights array, and resample that too (adding, not averaging)
    """
    # Construct slices for even and odd elements, respectively
    # e, o = np.s_[:,-1,2], np.s_[1,:,2] # Just learnt about the np.s_() function!
    e, o = slice(None,-1,2), slice(1,None,2)

    # Find the number of good sub-pixels in each new pixel
    ngood = mask[e,e].astype(int) + mask[o,e].astype(int) \
            + mask[e,o].astype(int) + mask[o,o].astype(int)

    newmask = ngood >= mingood
    # # Resample the mask
    # # newmask is True if any of the 4 sub-pixels are true
    # newmask = mask[e,e] | mask[o,e] | mask[e,o] | mask[o,o]

    if weights is None:
        # now resample the images
        newimages = [
            np.where(
                newmask,      # Check that we have at least 1 good pixel
                # Take the mean of all the good sub-pixels
                (image[e,e]*mask[e,e] + image[o,e]*mask[o,e]
                 + image[e,o]*mask[e,o] + image[o,o]*mask[o,o]) / ngood,
                0.0                 # Avoid NaNs if we have no good pixels
                )
            for image in images]
    else:
        newweights = (weights[e,e]*mask[e,e] + weights[o,e]*mask[o,e]
                      + weights[e,o]*mask[e,o] + weights[o,o]*mask[o,o])
        newimages = [
            np.where(
                newweights > 0.0,      # Check that we have at least 1 good pixel
                # Take the mean of all the good sub-pixels
                (image[e,e]*mask[e,e]*weights[e,e] +
                 image[o,e]*mask[o,e]*weights[o,e] +
                 image[e,o]*mask[e,o]*weights[e,o] +
                 image[o,o]*mask[o,o]*weights[o,o]
                 ) / newweights,
                0.0                 # Avoid NaNs if we have no good pixels
                )
            for image in images]

    if verbose:
        print("Fraction of good pixels: old = {:.2f}, new = {:.2f}".format(
            float(mask.sum())/mask.size, float(newmask.sum())/newmask.size))
    # Of course, we will get garbage where ngood=0, but that doesn't
    # matter since newmask will be False for those pixels
    if weights is None:
        return newimages, newmask
    else:
        # New option to bin weights too
        return newimages, newmask, newweights


def oversample(image, m):
    "Oversample an image by factor m x m. Simply repeat the pixels"
    # Check inputs
    if np.isnan(image).any():
        print("oversample: nan(s) found in input image")
    result = np.kron(image, np.ones((m,m)))
    # Check output
    if np.isnan(result).any():
        print("oversample: nan(s) found in output image")
    return result

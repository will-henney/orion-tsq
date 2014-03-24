from __future__ import print_function
import numpy as np
from astropy.io import fits
from astropy.table import Table
import lmfit
from matplotlib import pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import json
import sys 
sys.path.insert(0, '../../RingNebula/WFC3/2013-Geometry')
from photom_utils import model, \
    model_minus_data, \
    init_gauss_component, \
    LARGE_VALUE, init_poly_component


def store_component(db, params, section, clabel, ctype="gauss"):
    """
    Update db with a single spectrum component
    """
    if not clabel in db[section]:
        db[section][clabel] = {}
    d = db[section][clabel]
    suffix = "_{}_{}".format(ctype, clabel)
    d.update(
             Species=species_dict.get(clabel, "Glow"),
             Flux=params['area'+suffix].value,
             dFlux=params['area'+suffix].stderr,
             Wav=params['u0'+suffix].value,
             dWav=params['u0'+suffix].stderr,
             Wav0=params['u0'+suffix].init_value,
             Sigma=params['sigma'+suffix].value,
             dSigma=params['sigma'+suffix].stderr,
             )
    if ctype == "gauss":
        d.update(
            Sat=params['saturation'+suffix].value,
            dSat=params['saturation'+suffix].stderr,
            )
    

def store_poly_component(db, params, section, clabel="Power Law"):
    if not clabel in db[section]:
        db[section][clabel] = {}
    db[section][clabel].update(
        C0=params["p0"].value, dC0=params["p0"].stderr,
        C1=params["p1"].value, dC1=params["p1"].stderr,
        C2=params["p2"].value, dC2=params["p2"].stderr,
    )


def store_all_components(db, params, section):
    for clabel in gauss_components:
        store_component(db, params, section, clabel)
    store_poly_component(db, params, section)
        

def fit_continuum(wavs, spec, cmask, npoly=4):
    cont_coeffs = np.polyfit(wavs[cmask], spec[cmask], npoly)
    return np.poly1d(cont_coeffs)(wavs)


# Read in the emission line rest wavelengths
line_table = Table.read("orion-line-wavelengths.tab", 
    format="ascii.no_header", delimiter="\t",
    names=('lineid', 'linewav')
    )

# Read in list of line-free wav ranges for the continuum fitting
cont_table = Table.read("clean-continuum-ranges.tab", 
    format="ascii.no_header", delimiter="\t",
    names=('wav1', 'wav2')
    )

# Box that comfortably covers the sweet spot
box_x, box_y = -43.0, -48.0     # Center of box in arcsec: dRA, dDEC
box_w, box_h = 60.0, 60.0       # Box width and height, in arcsec
THRESH = 1.e-13                 # Threshold for possible saturation of long exposures

sections = {}
# This is different from the slit observations, since each band is done separately
for longband, band in ("red", "r"), ("green", "g"), ("blue", "b"):
    thdu = {
        "long": fits.open("Manu-Data/M42_{}/table_M42_l{}.fits".format(longband, band))[1],
        "short": fits.open("Manu-Data/M42_{}/table_M42_s{}.fits".format(longband, band))[1],
    }
    hdu = {
        "long": fits.open("Manu-Data/M42_{}/M42_l{}.fits".format(longband, band))[0],
        "short": fits.open("Manu-Data/M42_{}/M42_s{}.fits".format(longband, band))[0],
    }

    # First filter out fibers based on position.  We will take a 60 x
    # 60 arcsec box, centered on 5:35:13.592, -5:24:11.04
    mask = (np.abs(thdu["long"].data.dRA - box_x) <= box_w/2) &  \
           (np.abs(thdu["long"].data.dDEC - box_y) <= box_h/2)
    # Collect only the masked fibers
    tabdata = thdu["long"].data[mask]
    tabdata_s = thdu["short"].data[mask]
    specdata = hdu["long"].data[mask]
    specdata_s = hdu["short"].data[mask]
    # Use short exposure for the brightest pixels
    specdata[specdata > THRESH] = specdata_s[specdata > THRESH]

    # Set up wavelength coordinates - Angstrom
    nx, wav0, i0, dwav = [hdu["long"].header[k] for k in 
                          ("NAXIS1", "CRVAL1", "CRPIX1", "CDELT1")]
    wavs = wav0 + (np.arange(nx) - (i0 - 1))*dwav 

    # Create a wavelength mask containing clean continuum regions
    cmask = np.zeros_like(wavs, dtype=bool)
    for wav1, wav2 in cont_table:
        cmask = cmask | ((wavs > wav1) & (wavs < wav2))

    # Create one section for each fiber position in each of the three bands
    for spectrum, metadata in zip(specdata, tabdata):
        # Key is formed from the band and the position, in 1/10 of
        # arcsec: e.g., green-0013-0104 for (dRA, dDEC) = (-1.3,
        # -10.4)
        key = "{:s}{:+05d}{:+05d}".format(longband, int(10*metadata.dRA), int(10*metadata.dDEC))
        section = {}
        sections[key] = section
        section["x"] = metadata.dRA
        section["y"] = metadata.dDEC
        section["aperture"] = int(metadata.id_ap)
        section["band"] = band
        # Multiply by 1e15 as with the Helix to make the spectra of order unity for weak lines
        section["mean"] = 1.e15*spectrum/metadata.factor2
        # We don't have a good estimate of the std of the data - so make something up!
        section["std"] = 0.01*np.ones_like(spectrum)
        # Fit continuum to the clean wav ranges
        section["cont"] = fit_continuum(wavs, section["mean"], cmask)
        section["mean"] -= section["cont"]



species_dict = {}
for c in line_table:
    id_ = str(int(c['linewav']+0.5))
    species_dict[id_] = c['lineid']

wavranges = [
    ["FQ436N, FQ437N", 4250.0, 4500.0, "b"],
    ["F469N", 4500.0, 4800.0, "bg"],
    ["F487N", 4800.0, 4900.0, "g"],
    ["F502N", 4900.0, 5100.0, "g"], 
    ["F547M short", 5150.0, 5400.0, "g"],
    ["F547M mid", 5350.0, 5650.0, "g"],
    ["FQ575N, F547M long", 5650.0, 6000.0, "r"],
    ["F656N, F658N", 6400.0, 6650.0, "r"],
    ["F673N", 6640.0, 6760.0, "r"],
    ]

# drop_these = ["3968", "4686", "4922", "5192", "5412", "5846", "6312", "6398", "6500"]
drop_these = ["4649", "4511", "4591", "4610", "6398"]
# For Orion, we also drop He II and Mg I and weaker O II
drop_these += ["4542", "4686", "4563", "4571", "4610", "4590"]
# [Ar IV]
drop_these += ["4711", "4740"] 
# More weak lines to drop - C II, He I, etc
drop_these += ["4267", "4388", "5342", "5412", "6435", "6527", "5680"]
saturation_level = 25.0
# possibly_saturated = ["4959", "5007", "6563", "6583"]
possibly_saturated = []

# Set up containers for the figures
nplots, nfigs = len(wavranges), len(sections)
nx = 3
ny = 1 + (nplots - 1)//nx
figures = {}
axes = {}
for section in sections:
    figures[section], axes[section] = plt.subplots(ny, nx)
    axes[section] = np.atleast_2d(axes[section])

# Do the fits
for iax, (wav_id, wavmin, wavmax) in enumerate(wavranges):
    print(wav_id, wavmin, wavmax)
    wav0s = np.array(line_table["linewav"])
    wav0s = wav0s[(wav0s > wavmin) & (wav0s < wavmax)]
    m = (wavs > wavmin) & (wavs < wavmax)
    for section in sections:
        print(section)
        flux = sections[section]["mean"]
        cont = sections[section]["cont"]
        sigma = sections[section]["std"]

        params = lmfit.Parameters()
        gauss_components = []
        init_poly_component(params, [0.0, 0.0, 0.0])
        for wav0 in wav0s:
            clabel = str(int(wav0+0.5))
            if clabel in drop_these:
                continue
            if clabel in possibly_saturated:
                saturation = saturation_level
            else:
                saturation = LARGE_VALUE
            gauss_components.append(
                init_gauss_component(params, 1.0, wav0, 4.0, clabel, 
                                     ubounds=(wav0-3.0, wav0+3.0),
                                     wbounds=(2.0, 8.0), saturation=saturation)
            )

        result = lmfit.minimize(model_minus_data, params, 
                                args=(wavs[m], flux[m], gauss_components),
                                xtol=1e-4, ftol=1e-4,
        )
        print(result.message)
        
        store_all_components(sections, params, section)
        
        # Need to address a 1D version of the axes array
        ax = axes[section].reshape((nx*ny))[iax]
#        lmfit.report_errors(params)
        ax.plot(wavs[m], cont[m]+ flux[m], label="data", lw=1.5, alpha=0.6)
        ax.plot(wavs[m], cont[m] + model(wavs[m], params, gauss_components),
                 "r", label="fit", lw=1.5, alpha=0.6)
        # plot the global continuum fit
        ax.plot(wavs[m], cont[m], ":k", label="global cont", lw=2, alpha=0.3)
        # and the continuum with local excess included
        ax.plot(wavs[m], cont[m] + model(wavs[m], params, []),
                "--k", label="local cont", lw=2, alpha=0.3)
        for i, c in enumerate(gauss_components):
            ax.annotate("{} {}".format(species_dict[c], c), 
                         (float(c), 0.0), 
                         xytext=(0, -14*(1 + (i % 3))), 
                         textcoords="offset points", 
                         ha="center", va="top", fontsize="x-small", 
                         arrowprops={"arrowstyle": "->", "facecolor": "red"})
            # Also save the value of the fitted local continuum excess
            # This is found from the model, but with the gauss_components omitted
            sections[section][c]["local continuum excess"] = model(float(c), params, [])
        ax.minorticks_on()
        ax.grid(ls='-', c='b', lw=0.3, alpha=0.3)
        ax.grid(ls='-', c='b', lw=0.3, alpha=0.05, which='minor')
        ymax = np.max(flux[m] + cont[m])
        ymin = np.min(flux[m] + cont[m])
        ax.set_ylim(-0.5*ymax, 1.5*ymax)
        # ax.set_ylim(ymin/1.1, 1.1*ymax)
        # ax.set_yscale('log')
        slit, pos = section.split('-')
        legtitle = "{} :: Slit = {} :: Section {}".format(wav_id, slit, pos)

        legend = ax.legend(title=legtitle,
                           fontsize="small", ncol=4, loc="upper left")
        legend.get_title().set_fontsize("small")        
        

# Put all the plots in just one multi-page PDF file
with PdfPages('manu-fits.pdf') as pdf:
    for section in sorted(sections):
        fig = figures[section]
        # Set axis labels along left and bottom edges only
        for ax in axes[section][-1,:]:
            ax.set_xlabel("Wavelength")
        for ax in axes[section][:,0]:
            ax.set_ylabel("Flux")

        fig.subplots_adjust(left=0.05, right=0.98, bottom=0.05, top=0.98)
        fig.set_size_inches(5*nx, 4*ny)
        pdf.savefig(fig)
        # fig.savefig("ring-focus-fits-{}.pdf".format(section))

for secdata in sections.values():
    m = (wavs > 5100.0) & (wavs < 5850.0)
    cont_F547M = np.mean(wavs[m]*secdata["cont"][m])
    secdata["F547M continuum lam Flam"] = cont_F547M
    for key, linedata in secdata.items():
        if not key in species_dict:
            # jump over anything that is not an emission line
            continue
        # Select a small window around the line for measuring the continuum
        wav_min = linedata["Wav"] - linedata["Sigma"]
        wav_max = linedata["Wav"] + linedata["Sigma"]
        m = (wavs > wav_min) & (wavs < wav_max)
        # This is the mean continuum from the whole-spectrum fit
        cont_mean = secdata["cont"][m].mean()
        linedata["global continuum"] = cont_mean
        # Calculate and store equivalent width
        # EWs are calculated without the local excess correction to
        # the continuum, since it just made things worse when I tried
        # it 
        linedata["EW"] = linedata["Flux"] / cont_mean
        linedata["dEW"] = linedata["dFlux"] / cont_mean
        # Calculate and store continuum color wrt F547M range
        linedata["Color"] = linedata["Wav"]*cont_mean / cont_F547M
        
    # we don't want these big arrays going into the JSON store
    del secdata["mean"]
    del secdata["std"]
    del secdata["cont"]


##
## Dump all the data to a JSON file
##
class NumpyAwareJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray) and obj.ndim <= 1:
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)

with open("manu_spectral_fit_db.json", "w") as f:
    json.dump(sections, f, indent=2, cls=NumpyAwareJSONEncoder)   

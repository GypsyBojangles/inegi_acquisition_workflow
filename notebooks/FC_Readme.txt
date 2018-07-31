#acquire a fortran copiler - in this case gnu-fortran
sudo apt-get install gfortran
#download FC app
git clone https://github.com/GeoscienceAustralia/fc

#compile and install
pip install .  --no-deps --global-option=build --global-option='--executable=/usr/bin/env python' --user

#you will also need numxpr
pip install --user numexpr

NOTE:
The endmembers included as part of Geoscience Australia's implementation of the Fractional Cover algorithm have been trained 
using Australian fieldsite data on Geoscience Australia's NBAR Surface Reflectance product. This app and notebook is for 
demonstration purposes only. A proper implementation of FC on USGS LEDAPS/LaSRC would require training/generation of endmembers
using LEDAPS and LaSRC data combined with fieldsite data for your region of interest.

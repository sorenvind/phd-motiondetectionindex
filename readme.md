# Motion Detection Index Testing

A set of applications built for testing the practical performance of an index built for storing motion detection data from surveillance video.
The tests have only been built and tested on Mac OS X, but should work across platforms.

## Programs

### vid2diff.py
Take a video file as input, and create a set of grayscale difference frames with a given frame rate.

### diffcompress.py
Create an index for a set of difference frames output from vid2diff.py. The index computes a set of histograms for the difference frames and compress the resulting set of histograms to the final index. Supports creating many variations of indices simultaneously (using different index parameters).

### compareHistVideoTime.py
Compare the time spent answering a query on a video file, versus the time spent answering a query with an index built by diffcompress.py.

## Dependencies
Stuff required to run diffcompress.py and vid2diff.py

### Python Packages
Use e.g. pip package manager to install.
    zlib
    bz2
    pylzma
    liblzma
    lz4
    snappy
    pywt
    numpy
    matplotlib
    opencv

You must also install OpenCV on Mac
    brew update
    brew tap homebrew/science
    brew install opencv
    add to ~/.profile: export PYTHONPATH="/usr/local/lib/python2.7/site-packages/:$PYTHONPATH"

### Command Line Packages
Requires following command line programs.
    snappy
    7z

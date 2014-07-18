import numpy as np
import fileops
import cv2
import os
import sys
import time

## Compare time spent answering a query fully.
## 1: Extract answer from video stored on disk by decompressing
##		(answered basically as in vid2diff, followed by region extraction)
## 2: Extract answer from histograms stored on disk
## 		(decompress histogram, query relevant point in correct regions)

## Parameters
# Region size
regSize = 16

# Some area of regions in which to search
"""queryArea = {
0: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
1: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
2: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
3: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
4: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
5: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
6: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
7: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
8: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
9: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
10: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
11: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
12: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
13: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
14: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
15: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
}"""
#queryArea = {4: [4,5,6,7,8], 5: [4,5,6,7,8], 6: [4,5,6,7,8]}
queryArea = {4: [7]}

# Fraction of pixels (in area) above threshold
thresholdFrac = 0.15

# Pixel value diff threshold
thresholdValue = 3


###############
## Parameters for raw video decompressor. Must fit precomputed data for histograms.
# Name of video file in tests/
inFileName="rain-1m.mp4"

# Input video file directory (HAS TO BE ABSOLUTE FOR cv2.VideoCapture TO WORK ON MAC OS X!)
inDir="/Users/sorenvind/Documents/work/research/MotionDetection/HistogramCompression/tests"

# The number of frames that should be between any diff-image. I.e. if 25fps and diffInterval=5, 5 diffs are created per second.
diffInterval=10


################################
# Perform query on stored histograms
################################
# Assumptions about what we're timing:
# - 1 frames stored / file
# - Layout: linear
# - Compression used: zlib
fileframes = "1"
layout = "linear"
compression = "zlib-6"

# Naming for stored histogram folder
print "HISTOGRAMS"
tt = time.time()

fmatches = []
inputHistogramPath=os.path.join(inDir, "diff-"+inFileName+"_"+str(diffInterval), "frames_"+fileframes, str(regSize), layout, compression)
dirlist = os.listdir(inputHistogramPath)
i = 0
for ff in dirlist:
	i+=1
	
	print "File: {}".format(i * diffInterval)
	
	filepath = os.path.join(inputHistogramPath, ff)
	
	match = fileops.queryOnCompressedHistogram(filepath, regSize, queryArea, thresholdValue, thresholdFrac)
	if match:
		fmatches.append(i*diffInterval)

timeHistograms = time.time() - tt
print "Histogram time: {}".format(timeHistograms)

################################
# Perform query directly on video
################################
print "VIDEO"
inputVideoPath=os.path.join(inDir, inFileName)
capture = cv2.VideoCapture(inputVideoPath)

# Detect length of video to stop it looping. This is a workaround from normal because the Mac can't detect the end of file (so it loops the video)
frames = capture.get(cv2.cv.CV_CAP_PROP_FRAME_COUNT)
fps = capture.get(cv2.cv.CV_CAP_PROP_FPS)

tt = time.time()

count = 1
success, first = capture.read()
matches = []

# Converts to YUV while only keeping Y channel
grayFirst = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
while count <= frames:
	# Skip a number of frames (until the next read will be on the diffInterval)
	while(count < frames and count % diffInterval != (diffInterval-1)):
		capture.grab() # Only grab, don't read. Allows us to skip decoding for the frame
		count += 1

	count += 1	
	success, second = capture.read()
	graySecond = cv2.cvtColor(second, cv2.COLOR_BGR2GRAY)

	print "File: {}".format(count)

	# Absolute difference
	diff = cv2.absdiff(graySecond, grayFirst)
	
	# Calculate histograms from data
	match = fileops.queryOnData(diff, regSize, queryArea, thresholdValue, thresholdFrac)
	if match:
		matches.append(count)
	
	first = second
	grayFirst = graySecond
	
timeVideo = time.time() - tt
print "Video time: {}".format(timeVideo)

out = "File: {}\n \
regSize: {}\n \
layout: {}\n \
fileframes: {}\n \
compression: {}\n \
framerate: {}\n \
thresholdValue: {}\n \
thresholdFraction: {}\n\n\n".format(inFileName, regSize, layout, fileframes, compression, diffInterval, thresholdValue, thresholdFrac)

out += "Histogram time: {}\n".format(timeHistograms)
out += "    Video time: {}\n".format(timeVideo)
out += "Histogram matches: \n{}\n\n".format(fmatches)
out += "    Video matches: \n{}\n\n".format(matches)

print out

with open(os.path.join("results", "queryTime_{}.txt".format(time.time())), "w") as of:
	of.write(out)



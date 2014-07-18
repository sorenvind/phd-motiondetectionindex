import numpy as np
import fileops
import cv2
import os

# General idea:
# - Read video file frame by frame.
# - Convert frames to grayscale.
# - Calculate diff-image by subtracting frames and write it to disk.
# - Output diffs are written to tests/diff-${inFileName}
# - Diffs are gray-scale, obtained from RGB by conversion to YUV and keeping Y channel

# Name of video file in tests/
inFileName="HALLWAY_A.mpg"

# Input video file directory (HAS TO BE ABSOLUTE FOR cv2.VideoCapture TO WORK ON MAC OS X!)
inDir="/Users/sorenvind/Documents/work/research/MotionDetection/HistogramCompression/tests"

# The number of frames that should be between any diff-image. I.e. if 25fps and diffInterval=5, 5 diffs are created per second.
diffInterval=10


###############################
# Do the magic!
outputPath=os.path.join(inDir, "diff-"+inFileName+"_{}".format(diffInterval))
fileops.ensureDir(outputPath)

inputPath=os.path.join(inDir, inFileName)
capture = cv2.VideoCapture(inputPath)

# Detect length of video to stop it looping. This is a workaround from normal because OS X can't detect the end of file (so it loops the video)
frames = capture.get(cv2.cv.CV_CAP_PROP_FRAME_COUNT)
fps = capture.get(cv2.cv.CV_CAP_PROP_FPS)

totalSize = 0
count = 1
success, first = capture.read()

# Converts to YUV while only keeping Y channel
grayFirst = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
while count <= frames:
	# Ignore a number of reads (until the next read will be on the diffInterval)
	while(count < frames and count % diffInterval != (diffInterval-1)):
		capture.grab()
		count += 1

	count += 1	
	success, second = capture.read()
	graySecond = cv2.cvtColor(second, cv2.COLOR_BGR2GRAY)

	
	# Absolute difference
	diff = cv2.absdiff(graySecond, grayFirst)
	
	# Show difference images as they are processed
	cv2.imshow("img", diff)
	k=cv2.waitKey(1)
	if k==27:
		break
	
	# Write to file
	outName = "diff_{}-{}_{:.1f}_{:04d}.bin".format(len(diff), len(diff[0]), fps/float(diffInterval), count) # diff_width-height_fps_count
	totalSize += fileops.diffToFile(outputPath, outName, diff)
	
	# Write progress
	print "Done generating diff {:>4}".format(count)
	
	first = second
	grayFirst = graySecond
	
print "Written to {}: {} kB".format(outputPath, totalSize/1024)

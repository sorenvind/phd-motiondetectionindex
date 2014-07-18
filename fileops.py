import numpy as np
import math as math
import subprocess as proc
import struct as struct
import snappy as snappy
import zlib as zlib
import bz2 as bz2
import pylzma as pylzma
import liblzma as xz
import lz4 as lz4
import sys
import os
import time

debug=False
colors=256

def ensureDirSub(path):
	try:
		os.makedirs(path)
	except OSError as e:
		return

	
def ensureDir(prefpath, sufpath=""):
	return ensureDirSub(os.path.join(prefpath, sufpath))

def isFile(prefpath, sufpath=""):
	return os.path.isfile(os.path.join(prefpath, sufpath))

def isEmpty(prefpath, sufpath=""):
	return os.path.getsize(os.path.join(prefpath, sufpath)) == 0
		
# Return the size of the directory at the given path.
# Only files in that directory is counted towards the size, not any subdirectories
def dirSize(path):
	return sum([os.path.getsize(os.path.join(path, f)) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])



# Read diff-data from given filename and at the same time record the histogram for each region.
# Data format: 	image diff is stored row-wise, with all pixels (from 0 to width-1) in row i 
#				directly preceding the pixels of row i+1. We assume diff values are positive in range 0-colors.
#
# Regions:		we calculate the region overlay on the image from regColumns and regRows. We assume these
#				values evenly divides the image. If not, remaining pixels will be put in the outermost regions.
#
# Output:		data = 2D matrix of all diff values. Index i, j = diff value at row i, column j.
#				regionHistograms = 	3D matrix of histograms. Index i, j = histogram array for region in row i, column j.
#									histogram array has length colors. Index k = number of diff values with value k in region.
#
# Width = width of image
# Height = height of image
# regColumns = number of region columns
# regRows = number of region rows
# colors = maximum value for diff-data
def dataFromFile(name, width, height):
	if debug:
		tt = time.clock()
	data = np.fromfile(name, dtype=np.ubyte).reshape((height, width))
	if debug:
		print "Time spent reading data (new): {}".format(time.clock()-tt)

	return data


def queryOnData(data, regCount, queryArea, thresholdValue, thresholdFrac):
	height = len(data)
	width = len(data[0])
	regWidth = width / regCount # Will round down to nearest int
	regHeight = height / regCount
	lastRegWidth = regWidth + width % regCount # Add the remaining pixels (may cause last region to be almost double size)
	lastRegHeight = regHeight + height % regCount
	
	if debug:
		print "regWidth {}, regHeight {}, lastRegWidth {}, lastRegHeight {}, regCount {}".format(regWidth, regHeight, lastRegWidth, lastRegHeight, regCount)
		
	# Assume queryArea is dict with keys = X-region, and values a list of Y-regions
	# Find the no. changed pixels above threshold for each query area, then sum those to answer query
	pixelsAboveValue = 0
	totalPixels = 0
	for i in sorted(queryArea.keys()):
		for j in queryArea[i]:
			# Note: The slicing here is numpy-specific. 
			thisWidth = regWidth
			thisHeight = regHeight
			
			# Detect if we're in the last row or column. Set remaining number of pixels for this region if so.
			if i == regCount-1:
				thisHeight = lastRegHeight
			if j == regCount-1:
				thisWidth = lastRegWidth
			
			matSlice = data[i*regHeight:(i*regHeight + thisHeight), j*regWidth:(j*regWidth + thisWidth)]
			
			regPixels = thisHeight * thisWidth
			regPixelsAboveValue = (thresholdValue <= matSlice).sum() # The fastest way to do this acc. to http://stackoverflow.com/questions/9560207/how-to-count-values-in-a-certian-range-in-a-numpy-array
			pixelsAboveValue += regPixelsAboveValue
			totalPixels += regPixels
			
			if debug:
				print "I: {} J: {} K: {}. Above: {}. Total: {}.".format(i, j, thresholdValue, regPixelsAboveValue, regPixels)
	
	# True if more then pct pixels changed more than threshold
	if debug:
		print "Above: {}. Total: {}.".format(pixelsAboveValue, totalPixels)
	return (pixelsAboveValue / float(totalPixels)) > thresholdFrac
	
def queryOnCompressedHistogram(filepath, regCount, queryArea, thresholdValue, thresholdFrac):
	dec_bytes = open(filepath, "rb").read()
	bytes = zlib.decompress(dec_bytes)
	
	data = np.frombuffer(bytes, dtype=np.int16).reshape((regCount, regCount, colors))
	
	# Assume queryArea is dict with keys = X-region, and values a list of Y-regions
	# Find the no. changed pixels above threshold for each query area, then sum those to answer query
	pixelsAboveValue = 0
	totalPixels = 0
	for i in sorted(queryArea.keys()):
		for j in queryArea[i]:
			pixelsBelowValue = data[i][j][thresholdValue-1]
			if thresholdValue == 0:
				pixelsBelowValue = 0
			#pixelsBelowValue = histValFromFileLinear(bytes, regCount, i, j, thresholdValue-1) # assume thresholdValue > 0
			
			regPixels = data[i][j][colors-1]
			#regPixels = histValFromFileLinear(bytes, regCount, i, j, colors-1) # get # pixels in histogram
			regPixelsAboveValue = regPixels - pixelsBelowValue
			pixelsAboveValue += regPixelsAboveValue
			totalPixels += regPixels
			
			if debug:
				print "I: {} J: {} K: {}. Above: {}. Total: {}.".format(i, j, thresholdValue, regPixelsAboveValue, regPixels)
	
	# True if more then pct pixels changed more than threshold
	if debug:
		print "Above: {}. Total: {}.".format(pixelsAboveValue, totalPixels)
	return (pixelsAboveValue / float(totalPixels)) > thresholdFrac
			
	

# Extract a single value from a byte sequence from a linearly stored file
"""def histValFromFileLinear(bytes, regCount, regionCol, regionRow, thresholdValue):
	intSize = struct.calcsize('H')

	# Index directly into the bytes array, grab the bytes that encode the value.
	# Note that the stored histograms are cumulative, counting the # pixels having value at most x in position x
	rowBytes = regionRow*regCount*colors # Offset for number of bytes in rows until i
	columnBytes = regionCol*colors # Offset for # bytes in columns until j
	offset = (rowBytes+columnBytes+thresholdValue)*intSize
	val = bytes[offset : offset + intSize] 
	pixelsBelow = struct.unpack_from('H', val) # always returns tuple, even for singletons
	return pixelsBelow[0]"""
		
		
def regionsFromData(data, regCount, colors):
	height = len(data)
	width = len(data[0])
		
	regionHistograms = np.zeros((regCount*regCount, colors))
	regWidth = width / regCount # Will round down to nearest int
	regHeight = height / regCount
	lastRegWidth = regWidth + width % regCount # Add the remaining pixels (may cause last region to be almost double size)
	lastRegHeight = regHeight + height % regCount
	
	if debug:
		print "regWidth {}, regHeight {}, lastRegWidth {}, lastRegHeight {}, regCount {}".format(regWidth, regHeight, lastRegWidth, lastRegHeight, regCount)
	
	if debug:
		tt = time.clock()
	for i in range(0, regCount):
		for j in range(0, regCount):
			# Note: The slicing here is numpy-specific. 
			thisWidth = regWidth
			thisHeight = regHeight
			
			# Detect if we're in the last row or column. Set remaining number of pixels for this region if so.
			if i == regCount-1:
				thisHeight = lastRegHeight
			if j == regCount-1:
				thisWidth = lastRegWidth
			
			matSlice = data[i*regHeight:(i*regHeight + thisHeight), j*regWidth:(j*regWidth + thisWidth)]
			hist, bins = np.histogram(matSlice, bins=np.arange(colors+1)) # the bins define both left and right edge (hence the +1)
			regionHistograms[i*regCount+j] = hist
	if debug: 
		print "Time to read data: {}".format(time.clock() - tt)

	if debug: 
		tt = time.clock()
	for i in range(0, len(regionHistograms)):
		regionHist = regionHistograms[i]
		cumRegionHist = np.cumsum(regionHist)
		regionHistograms[i] = cumRegionHist
	if debug: 
		print "Time for cumsums: {}".format(time.clock() - tt)

		
	return regionHistograms
	

# Take a list of region histograms and write all of them to a single file with the given basename.
# The function assumes a few things about the list of histograms:
#	- each value in the list is itself a list of all histograms in a single frame
# 	  and all histograms given in that list have the same length.
#	- i.e. hist = list of frame histograms, if len(hist)=10 the list has all histograms from 10 frames.
#	  hist[0] = the histogram for the first frame in the list
#	- the list of histograms for a single frame is one-dimensional (row-wise arranged)
#	- all values in individual histograms fit into a C Integer (i.e. 4 bytes)
def histToFileLayout(path, name, hist, layout, overwrite=False):
	pathLayout = os.path.join(path, layout)
	ensureDir(pathLayout)
	fileName = name+".hist."+layout
	
	if not isFile(pathLayout, fileName) or isEmpty(pathLayout, fileName) or overwrite:	
		bufferSize=len(hist)*len(hist[0])*len(hist[0][0])
		#intType = 'I' if globalBiggest > 64000 else 'H'
		#intType = 'B' if globalBiggest < 256 else 'H'
		intType = 'H' # Assume all numbers fit in a short (breaks if full hd and 4x4 regions)
		intSize = struct.calcsize(intType)
		bf = np.newbuffer(bufferSize*intSize)
		
		with open(os.path.join(pathLayout, fileName), "wb") as of:
			if layout == "linear":
				histToFileLinear(of, hist, intType, bf)
			elif layout == "binned":
				histToFileBinned(of, hist, intType, bf)
			elif layout == "reg-linear":
				histToFileRegionLinear(of, hist, intType, bf)
			elif layout == "reg-binned":
				histToFileRegionBinned(of, hist, intType, bf)
				
	return pathLayout, fileName
				
# Write the histograms in a linear fashion, first all histograms from the first frame, then from the second and so on	
def histToFileLinear(of, hist, intType, bf, selfTest=False):
	intSize = struct.calcsize(intType)
	writtenBytes = 0
	# Fill the buffer before writing
	for i in range(0, len(hist)):
		frameHists = hist[i]
	
		for j in range(0, len(frameHists)):
			cumRegionHist = frameHists[j]
			struct.pack_into(intType*len(cumRegionHist), bf, writtenBytes, *cumRegionHist)
			writtenBytes += intSize*len(cumRegionHist)
	of.write(bf)
	
	if selfTest:
		# Check that everything went correctly and that the histValFromFile method works
		for i in range(0, len(hist)):
			frameHists = hist[i]
			for j in range(0, len(frameHists)):
				for k in range(0, colors):
					byteval = histValFromFileLinear(bf, len(hist), i, j, k)
					realval = hist[i][j][k]
					if realval - byteval != 0:
						print "I: {} J: {} K: {}: Read {}. Expected {}.".format(i, j, k, byteval, realval)

# Write the histograms in a binned fashion, with all 0-values from all histograms for all frames written linearly followed by 1s and so on
def histToFileBinned(of, hist, intType, bf):
	intSize = struct.calcsize(intType)
	writtenBytes = 0
	# assume all histograms have same size.
	for k in range(0, len(hist[0][0])):
		# write each number k from all histograms across all frames after each other
		for i in range(0, len(hist)):
			frameHists = hist[i]		
		
			for j in range(0, len(frameHists)):
				cumRegionHist = frameHists[j]
				struct.pack_into(intType, bf, writtenBytes, cumRegionHist[k])
				writtenBytes += intSize
	of.write(bf)
					
# Write the histograms in a region-linear fashion. The same region is written linearly across all frames, followed by the next region.
def histToFileRegionLinear(of, hist, intType, bf):
	intSize = struct.calcsize(intType)
	writtenBytes=0
	# Assume all frames have an equal number of regions (statically located)
	for j in range(0, len(hist[0])):
		# Write the selected region j in all frames linearly
		for i in range(0, len(hist)):
			cumRegionHist = hist[i][j]
			struct.pack_into(intType*len(cumRegionHist), bf, writtenBytes, *cumRegionHist)
			writtenBytes += intSize*len(cumRegionHist)
	of.write(bf)
	
# Write the histograms in a region-binned fashion. The same region across all frames is written binned, followed by the next region.
def histToFileRegionBinned(of, hist, intType, bf):
	intSize = struct.calcsize(intType)
	writtenBytes=0
	# Assume all frames have an equal number of regions (statically located)
	for j in range(0, len(hist[0])):
	
		# Write the selected region j in all frames binned
		for k in range(0, len(hist[0][0])):
			for i in range(0, len(hist)):
				struct.pack_into(intType, bf, writtenBytes, hist[i][j][k])
				writtenBytes += intSize
	of.write(bf)


# Given a 2D matrix of diff values in the range 0-255, write them to the file at path/name
def diffToFile(path, name, diff):	
	totalSize = 0
	with open(os.path.join(path, name), "wb") as of:
		for i in range(0, len(diff)):
			diffRow = diff[i]

			# Each number is byte
			val = struct.pack('B'*len(diffRow), *diffRow)
			totalSize += len(val)
			of.write(val)
	
	return totalSize	


	

# Execute the given command for the compression given.
# Return the time spent to execute the command.
def compressAndTime(compression, command, bytes_read, path, fileName):	
	st = time.clock()
	bytes = eval(command)
	ut = time.clock() - st
	ensureDir(path, compression)
	with open(os.path.join(path, compression, fileName+"."+compression), "wb") as of:
		of.write(bytes)
	return ut
				
# Execute the given command for the compression given.
# Return the time spent to execute the command.
def decompressAndTime(compression, command, path, fileName):
	dec_bytes = open(os.path.join(path, compression, fileName+"."+compression), "rb").read()
	st = time.clock()
	bytes = eval(command) #decompress the bytes
	ut = time.clock() - st
	return ut
	
	
# Take the name of a file already written to disk with some layout, compress it using different algoritms.
# The path argument is the relative location of the folder the file is located in.
# We do not use the compression connectors from Python, instead relying on shell commands to ease compression.
# Output files are written to subfolders of the path argument
#
# Compression algorithms applied:
#	- zlib (SETTINGS)
#	- bzip2 (SETTINGS)
#	- snappy
#	- 7zip (Mix of bzip2, LZMA2, LZMA and others) (SETTINGS)
#	- rzip
#	- szip
#	- quickLZ
#	- LZO
#
# Return the time spent to do the different compressions, timed using time.clock(), in a dictionary
def compressFile(path, name):
	timings = {
		"snappy": {},
		"zlib-6": {"lib": "zlib"},
		"bz2-6": {"lib": "bz2"},
		"lzma": {"lib": "pylzma"},
		"lz4": {}
	}
	origFile = os.path.join(path, name)
	
	# Read bytes
	if debug:
		print "Compressing file {}".format(origFile)
	bytes_read = open(origFile, "rb").read()
	
	# Compress file with different compressors, and time them. Time spent reading/writing files is not included.
	for comp, timeDic in timings.iteritems():
		lib = timings[comp].get("lib", comp)
		timings[comp]["compress"] = compressAndTime(comp, lib+".compress(bytes_read)", bytes_read, path, name)
	
	
	# Also time decompression
	for comp, timeDic in timings.iteritems():
		lib = timings[comp].get("lib", comp)
		timings[comp]["decompress"] = decompressAndTime(comp, lib+".decompress(dec_bytes)", path, name)
		
	if debug:
		print "Done Compressing/Decompressing file {}".format(origFile)
		
	return timings
	
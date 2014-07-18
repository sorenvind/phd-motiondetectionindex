from PIL import Image, ImageDraw
import numpy as np
import math as math
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import pywt as pywt
import copy as copy
import wavecomp
import mischist
import fileops
import Queue as queue
import sys
import os
import argparse
from collections import namedtuple
from multiprocessing import Pool


#####################################################
###### HERE ARE THE OPTIONS THAT CAN BE CHANGED #####
#####################################################

# Video resolution
vidWidth = 704
vidHeight = 576

# Process all files in this directory
pp = "tests/diff-Stair.mpg_5"

# Regions per direction
regSizes = [4, 8, 16, 32]

# Frames per file
frames = [1, 10]

# Layout we want to store the histograms with
layouts = ["linear", "binned", "reg-linear", "reg-binned"]

# Compression algorithms we are interested in trying out. 
# The value defines how they are shown in graphs with matplotlib.
compressions = {"lz4": "ro--", "snappy": "go--", "bz2-6": "bo--", "zlib-6": "ko--", "lzma": "mo--"}

# Debugging
debug = False
#debug = True


#####################################################
##### HERE BE PARSING OF COMMAND LINE ARGUMENTS #####
#####################################################

parser = argparse.ArgumentParser(description='Arguments')
parser.add_argument('--height', dest='height', type=int, action='store', default=vidHeight, help='the height of the original video')
parser.add_argument('--width', dest='width', type=int, action='store', default=vidWidth, help='the width of the original video')
parser.add_argument('--regions', dest='regions', type=int, action='store', default=regSizes, nargs='+', help='a list of regions per direction')
parser.add_argument('--frames', dest='frames', type=int, action='store', default=frames, nargs='+', help='a list of # frames that should be stored per compressed file')
parser.add_argument('--layouts', dest='layouts', choices=["linear", "binned", "reg-linear", "reg-binned"], action='store', default=layouts, nargs='+', help='a list of layouts names in which the regions should be stored')
parser.add_argument('--dir', dest='pp', required=True, action='store', help='directory containing diffs to process')

args = parser.parse_args()
if debug:
	print "height: "+str(args.height)
	print "width: "+str(args.width)
	print "regions: "+str(args.regions)
	print "frames: "+str(args.frames)
	print "layouts: "+str(args.layouts)
	print "dir: "+args.pp


# Use the input arguments in place of the defaults (i.e. if they were changed, otherwise defaults are used)
vidHeight = args.height
vidWidth = args.width
regSizes = args.regions
frames = args.frames
layouts = args.layouts
if os.path.isdir(args.pp):
	pp = args.pp
else:
	print "Given directory {} is not valid".format(args.pp)
	sys.exit(0)

# Write where the results will be written
resultPath = "results"
resultPost = pp.split('/')[1]
if debug:
	print "Processing {}".format(pp)
	print "Writing results to directory {} with postfix {}".format(resultPath, resultPost)

# Cols = Different pixel values
cols = 256

# Only process regions where the region size evenly divides video size
#realReg = []
#for regSize in regSizes:
#	if not (vidWidth % regSize != 0 or vidHeight % regSize != 0):
#		realReg.append(regSize)
#regSizes = realReg

# Take two dictionaries and put all values from the second dictionary as new values in the lists of the first one.
# I.e. sumDict is a dictionary with lists as values, newDict has numbers as values
def recordTimingsFact(sumDict):
	def recordTimings(newDict):	
		for key, direction in newDict.iteritems():
			mergeList = {}
			if key in sumDict:
				mergeList = sumDict[key]
			# The things we are merging are in fact dictionaries, so we want to merge the values, not the keys.
			for k, v in direction.iteritems():
				if k == "lib":
					continue
				if not k in mergeList:
					mergeList[k] = []
				mergeList[k].append(direction[k])
			sumDict[key] = mergeList
	return recordTimings

# Result class, for storing data about a compression result.
class Res:
	def __init__(self, totalframes, fileframes, regions, layout, compression, origsize, totalsize, totaltimecompress, totaltimedecompress):
		self.totalframes = totalframes
		self.fileframes = fileframes
		self.regions = regions
		self.layout = layout
		self.compression = compression
		self.origsize = origsize
		self.totalsize = totalsize # in bytes!
		self.totaltimecompress = totaltimecompress
		self.totaltimedecompress = totaltimedecompress

	def toStr(self):
		return "{:>3}, {:>3}, {:>4}, {:>7}, {:>7}, {:>6.1f}, {:>8.4f}, {:>8.4f}\n".format(self.totalframes, self.fileframes, self.regions, self.layout, self.compression, self.totalsize/float(1024), self.totaltimecompress, self.totaltimedecompress)

	def ratio(self):
		return self.origsize / float(self.totalsize)
		
	def totalTime(self):
		return self.totaltimecompress + self.totaltimedecompress

# Given a list of items A and a list of filter key-value pairs (K, V), 
# yield an item from A if the item has a field named K with value V.
# Very usable to look through a list of objects and only get those fitting some criteria.
def filterList(itemlist, filterlist):
	for r in itemlist:
		passed = True
		for k, v in filterlist.iteritems():
			if getattr(r, k) != v:
				passed = False

		if passed:
			yield r


# Lists for storing several images worth of histograms, to experiment with compression of longer runs of data
histograms = {}
for f in frames:
	histograms[f] = {}

# For keeping all timings. 
allTimings = {}
for regSize in regSizes:
	allTimings[regSize] = {}
	for i in frames:
		histograms[i][regSize] = []
		allTimings[regSize][i] = {}
		for layout in layouts: 
			allTimings[regSize][i][layout] = {"individual": {}, "total": {}}

# Parallelization pool
proc = 8
pool = Pool(processes=proc)

# Ignore non-wanted files in dirlist and remove them to ensure correct operation
dirlist = os.listdir(pp)
ignlist = []
for ff in dirlist:	
	if ff == ".DS_Store" or ff == "compressionResults.txt":
		ignlist.append(ff)

	# ignore directories
	current_file = os.path.join(pp, ff)
	if not os.path.isfile(current_file):
		ignlist.append(ff)
		
dirlist = [n for n in dirlist if n not in ignlist]



#####################################################
###### HERE STARTS THE ACTUAL COMPRESSION WORK ######
#####################################################

# Process all files in directory with the given region size
filecount = 0
for ff in dirlist:
	# ignore directories
	current_file = os.path.join(pp, ff)
	filecount += 1
	
	# Read data from file (once!)
	data = fileops.dataFromFile(current_file, vidWidth, vidHeight)
	
	# Iterate over different numbers of regions.
	for regSize in regSizes:
		timings = allTimings[regSize]
		
		# Calculate histograms from data
		linearHist = fileops.regionsFromData(data, regSize, cols)
	
		# Output and compress a number of files simultaneously
		for i in histograms.keys():
			histograms[i][regSize].append(linearHist)
		
			# Write the regions in a file for this regionsize and number of histograms
			cp = os.path.join(pp, "frames_"+str(i), str(regSize))
			fileops.ensureDir(cp)
		
			if filecount % i == 0 or ff == dirlist[-1]:
				if debug:
					print "Processing {}, i {}, length {}, first {}, linear {}, file {}, regsize {}".format(filecount, i, len(histograms[i][regSize]), len(histograms[i][regSize][0]), len(linearHist), cp, regSize)
				
				# Output the histograms to disk with different layouts, and compress them
				for layout in layouts:
					path, fileName = fileops.histToFileLayout(cp, ff, histograms[i][regSize], layout, True) # True = overwrite
					pool.apply_async(fileops.compressFile, (path, fileName), callback=recordTimingsFact(timings[i][layout]["individual"]))
					
					
				#pathLinear, linear, pathBinned, binned, pathRegLin, reglin, pathRegBin, regbin = fileops.histToFile(cp, ff, histograms[i][regSize])
				
				if debug:
					print "Written to disk: {}".format(ff)
	
				# Compress the histograms using process pool, record timings
				#recordTimingsFact(timings[i]["linear"]["individual"])(fileops.compressFile(pathLinear, linear))
				#pool.apply_async(fileops.compressFile, (pathLinear, linear), callback=recordTimingsFact(timings[i]["linear"]["individual"]))
				#pool.apply_async(fileops.compressFile, (pathBinned, binned), callback=recordTimingsFact(timings[i]["binned"]["individual"]))
				#pool.apply_async(fileops.compressFile, (pathRegLin, reglin), callback=recordTimingsFact(timings[i]["reg-linear"]["individual"]))
				#pool.apply_async(fileops.compressFile, (pathRegBin, regbin), callback=recordTimingsFact(timings[i]["reg-binned"]["individual"]))
		
				histograms[i][regSize] = []
				
	print "Processed file {:>4}/{:>4}: {:<3.1f}%".format(filecount, len(dirlist), (100*filecount)/float(len(dirlist)))

# Wait for all compressors to finish	
pool.close()
pool.join()


#####################################################
########## HERE STARTS THE RESULTS ANALYSIS #########
#####################################################
results = []

##### Step 1: Analyse data written to disk. 
#####			Look through timings dictionary for this. Write results as Res objects to results list.
#####			Write results to disk as CSV before proceeding.

# Now lets analyze all the generated files and timings and write summaries to disk as csv.
outCSV = "# Frames, # Regions, Layout, Compression, Total Size (kB), Compression Ratio, Total Time, Compression Speed\n"
for regSize, timings in sorted(allTimings.iteritems()):
	#outString += "Number of regions: {} x {} = {}\n".format(regSize, regSize, regSize*regSize)
	for i, alli in sorted(timings.iteritems()):
		#outString += " Timings for "+str(i)+" images\n"
		for method, compressionTimes in alli.iteritems():
			#outString += "  Method: {}\n".format(method)
			fileops.ensureDir(os.path.join(pp, "frames_"+str(i), str(regSize), method))
			origSize = fileops.dirSize(os.path.join(pp, "frames_"+str(i), str(regSize), method))
			
			#outString += "  Uncompressed: {} kB\n".format(origSize/1024)
			# timings is a dict of ALL timings in i-method compression, with compression as keys and a list of timings.
			# String for compression-free data
			outCSV += "{:>3}, {:>4}, {:>7}, {:>7}, {:>6.1f}, {:>5.1f}, {:>8.4f}, {:>6.1f}\n".format(i, regSize*regSize, method, "none", origSize/float(1024), 1.0, 0.0, 0.0)
			for compression, times in sorted(compressionTimes["individual"].iteritems()):
				# Calculate total time spent on compression
				totalTimeCompress = np.sum(times["compress"])
				totalTimeDecompress = np.sum(times["decompress"])			
			
				# Calculate total size (in bytes)
				fileops.ensureDir(os.path.join(pp, "frames_"+str(i), str(regSize), method, compression))
				totalSize = fileops.dirSize(os.path.join(pp, "frames_"+str(i), str(regSize), method, compression))

				# Print the total time values
				outCSV += "{:>3}, {:>4}, {:>7}, {:>7}, {:>6.1f}, {:>5.1f}, {:>8.4f}, {:>6.1f}, {:>8.4f}, {:>6.1f}\n".format(i, regSize*regSize, method, compression, totalSize/float(1024), origSize/float(totalSize), totalTimeCompress, origSize/(1024*1024*totalTimeCompress), totalTimeDecompress, origSize/(1024*1024*totalTimeDecompress))
				newRes = Res(len(dirlist), i, regSize*regSize, method, compression, origSize, totalSize, totalTimeCompress, totalTimeDecompress)
				results.append(newRes)


fileops.ensureDir(resultPath)
with open(os.path.join(resultPath, "results_{}.csv".format(resultPost)), "w") as of:
	of.write(outCSV)

##### Step 2: Look at Res objects. Extract interesting data results from those.
#####			This is relatively simple to do using the filterlist function.
#####			Plot the results, write them to disk or whatever.

## Create diagrams and save them	
plt.rc('legend',**{'fontsize':6})
colors = ['b', 'r', 'g', 'k']
for framenum in frames:
	for regSize in regSizes:
		resultList = sorted(filterList(results, {"fileframes": framenum, "regions": regSize*regSize}), key=lambda x: x.compression)

		# Save a bar chart for compression ratio per second
		bars = np.arange(len(compressions.keys()))
		plt.clf()
		height = 0.8 / len(layouts)
		# Plot bars for all layouts in one plot ..
		for idx, layout in enumerate(layouts):
			ratios = [n.ratio()/n.totalTime() for n in resultList if n.layout==layout]
			plt.barh(bars-idx*(height)+3*height/2, ratios, height, align='center', color=colors[idx], alpha=0.3, label=layout)
		plt.legend()
		plt.yticks(bars, sorted(compressions.keys()))
		plt.xlabel('Ratio per second')
		plt.title('Compressor comparison\nDirectory: '+resultPost)
		
		plt.savefig(os.path.join(resultPath, "ratiopersecond_{}-frames_{}-layout_{}-regions_{}.png".format(framenum, '-'.join(layouts), regSize*regSize, resultPost)), dpi=200)

		# Save a bar chart for compression ratios
		bars = np.arange(len(compressions.keys()))
		plt.clf()
		# Plot bars for all layouts in one plot ..
		for idx, layout in enumerate(layouts):
			ratios = [n.ratio() for n in resultList if n.layout==layout]
			plt.barh(bars-idx*(height)+3*height/2, ratios, height, align='center', color=colors[idx], alpha=0.3, label=layout)
		plt.legend()
		plt.yticks(bars, sorted(compressions.keys()))
		plt.xlabel('Ratio')
		plt.title('Compressor comparison\nDirectory: '+resultPost)
		
		plt.savefig(os.path.join(resultPath, "ratio_{}-frames_{}-layout_{}-regions_{}.png".format(framenum, '-'.join(layouts), regSize*regSize, resultPost)), dpi=200)

		# Save a bar chart for compression times
		bars = np.arange(len(compressions.keys()))
		plt.clf()
		# Plot bars for all layouts in one plot ..
		for idx, layout in enumerate(layouts):
			ratios = [n.totaltimecompress for n in resultList if n.layout==layout]
			plt.barh(bars-idx*(height)+3*height/2, ratios, height, align='center', color=colors[idx], alpha=0.3, label=layout)
		plt.legend()
		plt.yticks(bars, sorted(compressions.keys()))
		plt.xlabel('Compression time')
		plt.title('Compressor comparison\nDirectory: '+resultPost)
		
		plt.savefig(os.path.join(resultPath, "compress_{}-frames_{}-layout_{}-regions_{}.png".format(framenum, '-'.join(layouts), regSize*regSize, resultPost)), dpi=200)

		# Save a bar chart for decompression times
		bars = np.arange(len(compressions.keys()))
		plt.clf()
		# Plot bars for all layouts in one plot ..
		for idx, layout in enumerate(layouts):
			ratios = [n.totaltimedecompress for n in resultList if n.layout==layout]
			plt.barh(bars-idx*(height)+3*height/2, ratios, height, align='center', color=colors[idx], alpha=0.3, label=layout)
		plt.legend()
		plt.yticks(bars, sorted(compressions.keys()))
		plt.xlabel('Decompression time')
		plt.title('Compressor comparison\nDirectory: '+resultPost)
		
		plt.savefig(os.path.join(resultPath, "decompress_{}-frames_{}-layout_{}-regions_{}.png".format(framenum, '-'.join(layouts), regSize*regSize, resultPost)), dpi=200)


for layout in layouts:
	# Only consider a layout at a time. Only consider zlib-6 compression
	resultList = sorted(filterList(results, {"layout": layout, "compression": "zlib-6"}), key=lambda x: x.regions)

	# Create a chart for ratio depending on region sizes.
	# Each line should be the number of frames data is stored in.
	# The y-coordinate on each axis is the total size of the data stored after compression (in mb)
	fig, axes = plt.subplots()
	xs = [n*n for n in regSizes]
	for idx, framenum in enumerate(frames):
		ys = [n.totalsize/(float(n.regions*n.totalframes)) for n in resultList if n.fileframes==framenum]
		print "{} fileframes, bytes per region: {}".format(framenum, str(ys))
		axes.plot(xs, ys, colors[idx]+"o--", label="{} frames/file".format(framenum))
	axes.legend()	
	axes.set_ylabel("Space in bytes per region on average")
	axes.set_xlabel("Number of regions")
	plt.title('Compressor comparison\nDirectory: '+resultPost)
	
	plt.savefig(os.path.join(resultPath, "regionsizes_{}-frames_{}-layout_{}-regions_{}.png".format('-'.join(map(str, frames)), layout, '-'.join(map(str, regSizes)), resultPost)), dpi=200)

	
	
"""
fig, axes = plt.subplots(4, sharex=True)
xs = [n*n for n in regSizes]
axes[0].set_ylabel("Space (in MB)")
for comp, col in compressions.iteritems():
	ys = [n.totalsize/float(1024*1024) for n in regionComparison if n.compression==comp]
	axes[0].plot(xs, ys, col, label=comp)
axes[0].legend()

axes[1].set_ylabel("Ratio")
for comp, col in compressions.iteritems():
	ys = [n.ratio() for n in regionComparison if n.compression==comp]
	axes[1].plot(xs, ys, col, label=comp)
axes[1].legend()

axes[2].set_ylabel("Compression Time (in s)")
for comp, col in compressions.iteritems():
	ys = [n.totaltimecompress for n in regionComparison if n.compression==comp]
	axes[2].plot(xs, ys, col, label=comp)
axes[2].legend()

axes[3].set_ylabel("Decompression Time (in s)")
axes[3].set_xlabel("Number of regions")
for comp, col in compressions.iteritems():
	ys = [n.totaltimedecompress for n in regionComparison if n.compression==comp]
	axes[3].plot(xs, ys, col, label=comp)
axes[3].legend()

fig.suptitle("Layout: {}, Frames: {}\n".format(layout, framenum))
fig.tight_layout()
plt.savefig(os.path.join(resultPath, "{}-frames_{}-layout.png".format(framenum, layout)), dpi=200)
"""

""" 
THE FOLLOWING SHOWS HOW TO PERFORM WAVELET COMPRESSION AND SHOWS GRAPHS
NOTE: regionHistograms is a 2D matrix of histograms just as returned by fileops.datafromfile()

# Compress each region seperately
for i in range(0, len(regionHistograms)):
	for j in range(0, len(regionHistograms[0])):
		cumRegionHist = regionHistograms[i][j]
		regionHist = np.diff(cumRegionHist)
		classify = wavecomp.createCompressions(regionHist, cumRegionHist, False, True, True, "("+str(i)+", "+str(j)+")", 0.95, 10)


fig = plt.figure()
plt.imshow(data)
#plt.set_cmap('gray')
for i in range(regCols):
	plt.plot([i*vidHeight/regCols]*vidWidth, 'w-')
for i in range(regRows):
	plt.plot([i*vidWidth/regRows]*vidHeight, range(0, vidHeight), 'w-')
	
plt.show()
"""
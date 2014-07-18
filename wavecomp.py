import numpy as np
import math as math
import pywt as pywt
import copy as copy


class Comp:
	def __init__(self, hist, recHist, diff, quality, method, settings, size, coord):
		self.hist = hist
		self.recHist = recHist
		self.diff = diff
		self.quality = quality
		self.method = method
		self.settings = settings
		self.size = size
		self.coord = coord
		
	def plot(self, plot):
		mischist.plotHistogram(plot, self.hist, self.recHist, self.diff, self.quality, self.method, self.settings, self.size, self.coord)


# Given a diffstring (of two cumulative histograms), calculate some quality measure
# Measure consist of difference between a number of more or less arbitrary points
# Thus, lower quality is better.
def calculateQuality(diff):
	qual = diff[4] + diff[9] + diff[29] + diff[99]
	return qual



# Classify a histogram. Detect the fraction of pixels having at most a certain value.
def classifyHist(cumHist, maxVal):
	return (cumHist[maxVal]) / cumHist[len(cumHist)-1]

def createCompressions(hist, cumHist, buckets, plot, log, coord, plotBreakFraction, plotBreakMaxVal):
	solutions = queue.PriorityQueue()

	classify = classifyHist(cumHist, plotBreakMaxVal)
	if classify > plotBreakFraction:
		return classify

	# Now, let's create all built-in wavelet compressions
	# Sort them by quality of compression and space usage.
	for family in pywt.families():
		for wave in pywt.wavelist(family):
			for compression in range(0, 8):	
				restoredCoeffs, recCumHist, stored, traildel, coeffs = generateCompression(cumHist, wave, compression)
		
				if stored > 40:
					continue
		
				# restore approximate histogram from cumulative
				recHist = np.diff(recCumHist)
					
				# calculate quality as sum of cumulative differences
				# note: lower is better for quality
				diff = np.absolute(np.subtract(cumHist, recCumHist))
				quality = calculateQuality(diff)
			
				# push the solution to the solutions-queue
				thisSol = Comp(hist, recHist, diff, quality, "wave ("+wave+")", "compression ("+str(compression)+"), traildel ("+str(traildel)+")", "size: "+str(stored)+", max 10: {:.2%}".format(classifyHist(cumHist, 10)), coord)
				solutions.put((quality, thisSol)) 
	
				if log:
					classify = classifyHist(cumHist, 10)
					print "Region "+coord+" Classify (max 10): "+str(classify)+" Quality: "+str(quality)
				
		
	# Also create a compression just based on reducing the number of buckets (if flag set)
	if buckets:
		res = 4
		bucCumHist = np.zeros(len(cumHist)/res)
		bucCumHist[0] = cumHist[0]
		for i in range(1, len(bucCumHist)):
			bucCumHist[i] = cumHist[i*res]

		recBucCumHist = np.zeros(len(cumHist))
		for i in range(0, len(recBucCumHist)):
			ind = math.floor(i/res)
			recBucCumHist[i] = bucCumHist[ind]
			# Add linear approximation ..
			if ind < len(bucCumHist)-1:
				recBucCumHist[i] += (i % res) * ((bucCumHist[ind+1] - bucCumHist[ind])/res)

		recHist = np.diff(recBucCumHist)

		diff = np.absolute(np.subtract(cumHist, recBucCumHist))
		quality = calculateQuality(diff)

		# plot the bucket solution
		bucketSol = Comp(hist, recHist, diff, quality, "buckets", "equal-spaced, under-approximation", "size: "+str(stored)+", max 10: "+classifyHist(len(bucCumHist), 10), coord)
		bucketSol.plot(plt)

	# plot the best solution seen
	solutions.get()[1].plot(plt)

	# return classification
	return classify

# Function for generating a wavelet compression.
# cumHist is the cumulative histogram, wavelet is the wavelet to use, compression is the number of coefficients to store
def generateCompression(cumHist, wavelet, compression):
	# Do a full multilevel wavelet decomposition until some level/resolution
	coeffs = pywt.wavedec(cumHist, wavelet)

	# Reduce trailing equal values from vectors
	vectors, lengths = reduceVectors(coeffs, 0.01)

	# Overwrite least significant detail coefficients in coeffs with 0-arrays (simulating removal)
	if compression < len(vectors):
		for i in range(compression,len(vectors)):
			arraySize = len(vectors[i])
			vectors[i] = np.zeros(arraySize)
	
	# Generate statistics
	stored = len(lengths)
	traildel = 0
	for i in range(0,min(len(vectors), compression)):
		stored += len(vectors[i])
		traildel += lengths[i] - len(vectors[i])
	
	# Restore trailing equal values
	restoredCoeffs = restoreVectors(vectors, lengths)

	# Do a full multilevel wavelet reconstruction from coeffs (zero-padded)
	recCumHist = pywt.waverec(restoredCoeffs, wavelet)
	return restoredCoeffs, recCumHist, stored, traildel, coeffs

# Given a set of vectors, remove trailing values that are equal
# Return the new vectors, and a length-vector for restoring original vectors
def reduceVectors(coeffs, threshold):
	# For each detail coefficient vector, remove trailing values with equal value
	red = copy.deepcopy(coeffs)
	lengths = np.zeros(len(coeffs))
	for i in range(0,len(coeffs)):
		detail = coeffs[i]
		lengths[i] = int(len(detail))
		if lengths[i] < 4:
			continue
			
		prev = len(detail)-1
		for j in range(len(detail)-2, 0, -1):
			#print "checking i, j, prev: "+str(i)+", "+str(j)+", "+str(prev)
			#print str(detail[prev]-detail[j])
			if math.fabs(detail[j] - detail[prev]) < threshold:
				prev = j
			else:
				red[i] = detail[:prev]
				break
	
	return red, lengths


# Restore trailing values of reduced vectors
def restoreVectors(coeffs, lengths):	
	# Restore the trailing values ..
	for i in range(0,len(coeffs)):
		detail = coeffs[i]
		elem = detail[len(detail)-1]
		newarr = [elem]*(lengths[i]-len(detail))
		coeffs[i] = np.append(detail, newarr)
		
	return coeffs

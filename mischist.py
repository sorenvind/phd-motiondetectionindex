import numpy as np
import math as math
import matplotlib.pyplot as plt
import matplotlib.patches as patches

def plotHistogram(plt, hist, recHist, diff, quality, method, settings, stored, coord):
	left, width = .25, .5
	bottom, height = .25, .5
	right = left + width
	top = bottom + height

	fig = plt.figure()
	ax = fig.add_axes([0.1,0.1,0.8,0.8])

	# axes coordinates are 0,0 is bottom left and 1,1 is upper right
	p = patches.Rectangle(
	    (left, bottom), width, height,
	    fill=False, transform=ax.transAxes, clip_on=False
	    )
	
	ax.text(right, top, 'method: '+str(method)+"\nsettings: "+str(settings)+"\n"+str(stored)+"\nquality: {:.2f}\ncoordinates: {}".format(quality, coord),
	        horizontalalignment='right',
	        verticalalignment='top',
	        transform=ax.transAxes)
	
	# plot vectors
	plt.plot(hist, 'black')
	plt.plot(recHist, 'r')
	plt.plot(diff, 'b')
	
	
def getRandomCumHist(numValues, cols):
	# Create random pixel values
	shape, scale = 2., 12. # mean and dispersion
	randPixels = np.random.gamma(shape, scale, numValues)

	# Generate histogram for raw data.
	buckets = np.arange(cols+1)

	# Create histogram and its cumulative version for the real data
	hist, edges = np.histogram(randPixels, bins=buckets)
	cumHist = np.cumsum(hist)
	
	return hist, cumHist

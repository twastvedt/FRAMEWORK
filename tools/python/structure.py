"""
Structure Class
for lap_joint script

Structure:
	.posts      list            list of all Posts in Structure
	.joints     dictionary      dictionary of all joints in Structure (key: 'p0,p1')
	.dim        int             number of Posts in Structure
	.maxId		int				maximum post id
	
Functions:
	.selectAxes     -       
	.orderAxes      -       
	.axesToPosts    -       
	
"""

import Rhino
import scriptcontext as sc
import rhinoscriptsyntax as rs
import System.Guid

from copy import deepcopy
from copy import copy

from collections import OrderedDict

import common
from joint import *
from post import *

class Structure:
	"""Just one of these. This holds all information (Posts, Joints, Notches)
		for an entire structure"""
	
	def __init__(self):
		"""Initialize a Structure"""
		
		self.posts = OrderedDict()
		self.joints = []
		
		self.dim = 0
		self.maxId = 0
		
	###########
	#Structure Class Functions
	
	def info(self):
		"""Displays a text summary of this Structure."""
		
		print "Structure: " + \
		" Posts: " + str(len(self.posts)) + \
		" Joints: " + str(len(self.joints)) + \
		"\n----"
	
	def display(self):
		"""Create objects in viewport to display information about this Structure
		
		Creates: nothing!
		
		"""
	
	def selectAxes(self):
		"""Allow the selection of lines representing post axes.
			Adds objects to structure as unordered list of lines
		"""
		
		axes = Rhino.Input.RhinoGet.GetMultipleObjects("Select Post Axes.", True, 
			Rhino.DocObjects.ObjectType.AnyObject)[1]
		
		self.axes = {}
		
		for axis in axes:
			try: 
				id = int(axis.Object().Name)
			except ValueError:
				raise NameError("Currently, un-numbered axes are not supported!")
				return True
				#unNumbered = True
				#self.unnumberedAxes.append(
				#	Rhino.Geometry.Line(axis.PointAtStart, axis.PointAtEnd))
				
			axis = axis.Object().CurveGeometry
			
			self.axes[id] = Rhino.Geometry.Line(axis.PointAtStart, axis.PointAtEnd)
			
			self.maxId = max(self.maxId, id)
			self.dim += 1		
		
		#sort axes by id
		self.axes = OrderedDict(sorted(self.axes.items(), key=lambda i: i[0]))
		
		return False
		
	def orderAxes(self):
		"""Assign labels to axes, ordering them along a vector.
			Orders self.axes and optionally adds names to Rhino objects.
		"""
		print "Define sort direction."
		result = Rhino.Input.RhinoGet.GetLine()
		if result[0] == Rhino.Commands.Result.Success:
			sortLine = result[1]
		else:
			raise NameError("Unable to get line for sort axis.")
		
		def sortFunction(axis):
			plane = Rhino.Geometry.Plane(sortLine.From, 
				Rhino.Geometry.Vector3d(sortLine.To - sortLine.From))
			return plane.DistanceTo(axis.PointAt(.5))
		
		self.axes.sort(key=sortFunction)
	
	def axesToPosts(self):
		"""turn all axes in self.axes into posts"""
		
		for key in self.axes:
			if self.axes[key] != None:
				p = Post(axis=self.axes[key], width=common.settings.main['postWidth'], 
					height=common.settings.main['postWidth'], id=key)
				self.addPost(p)
	
	def findPairs(self):
		"""Find all pairs of Posts in Structure which might intersect
		
		Returns: list of lists, each with two posts
		"""
		
		pairs = []
		keys = self.axes.keys()
		
		#loop through indeces of each Post
		for a in range(0, self.dim):
			#loop through all remaining Posts (higher indices)
			for b in range(a+1, self.dim):
				#only accept pairs within specified distance
				if rs.Distance(*common.findClosestPoints(self.posts[keys[a]].axis, 
					self.posts[keys[b]].axis)) < 2:
					pairs.append((keys[a], keys[b]))
					self.connections[keys[a]][keys[b]] = [[keys[b]]]
					self.connections[keys[b]][keys[a]] = [[keys[a]]]
		
		return pairs
	
	def makePockets(self, pocketClass):
		"""Make all Joints and Pockets necessary for current Structure
			Decide gender of pockets for joints which matter
			thanks to blokhead for the script, originally in perl
				(http://www.perlmonks.org/?node_id=522270)
		"""
		
		#initialize connection matrix
		self.connections = [[[[]] for i in range(self.maxId+1)] 
			for j in range(self.maxId+1)]
		
		#get all potential Joint pairs
		pairs = self.findPairs()
		
		###
		#assign genders to pockets and make joints
		
		#compute the 3rd power of the adjacency matrix with our modified multiplication
		current = deepcopy(self.connections)
		
		"""modified matrix multiplication. instead of multiplication, we
			combine paths from i->k and k->j to get paths from i->j (this is why
			we include the endpoint in the path, but not the starting point).
			then instead of addition, we union all these paths from i->j
		"""
		
		result1 = [[None for i in range(self.maxId+1)] for j in range(self.maxId+1)]
		for row in range(self.maxId+1):
			for column in range(self.maxId+1):
				new_paths = []
				for item in range(self.maxId+1): #connect new paths to all old paths
					for path in current[row][item]:
						for pathEnd in self.connections[item][column]:
							if pathEnd and pathEnd[0] != row: #weed out A-B-A paths
								new_paths.append(path + pathEnd)
				result1[row][column] = new_paths
		
		paths = [[None for i in range(self.maxId+1)] for j in range(self.maxId+1)]
		for row in range(self.maxId+1):
			for column in range(self.maxId+1):
				new_paths = []
				for item in range(self.maxId+1): #connect new paths to all old paths
					for path in result1[row][item]:
						for pathEnd in self.connections[item][column]:
							if pathEnd and len(path) == 2 and pathEnd[0] != path[-2]: #weed out A-B-C-B paths
								new_paths.append(path + pathEnd)
				paths[row][column] = new_paths
		
		#self.printPaths(paths)
		#keep track of desired pocket genders
		genders = {}
		
		for post in range(self.maxId+1):
			for path in paths[post][post]:
				#loop through each entry in matrix which represents a circular path of length three
				#check for partially connected rings
				dup = 0
				
				if len(path) == 3: #this post is part of a minor figure
					for i in range(3): #loop through 3 joints in figure
						p0 = path[i]
						p1 = path[(i+1) % 3]
						
						#gender relationship is same for two joints on figure,
						# different for the third (i == 0)
						gender = (i != 0)
						
						if p0 > p1: #pair ids are not in order
							p0,p1 = p1,p0
							gender = not gender
						if (p0,p1) in genders: #already decided this ring
							dup = 1
						else:
							if dup == 1: #bad. two minor figures are connected but not identical
								print "Connected rings at joint ({0}, {1})".format(p0,p1)
							genders[(p0,p1)] = gender
		#create all joints
		fringe = []
		for pair in pairs:
			if pair in genders:
				gender = genders[pair]
			else: #joint not in a minor figure
				fringe.append(pair)
				#assign default gender relationship
				gender = 0
			
			if gender:
				#reverse pair order to invert male/female relationship
				pair = pair[::-1]
			#create pockets for this joint
			self.joints.append(Joint(self.posts[pair[0]], self.posts[pair[1]], len(self.joints),
				pocketClass=pocketClass))
		
		print "Joints not in a complete minor figure: \n", fringe
	
	def printPaths(self, connections):
		"""the i,j entry of the matrix is a list of all the paths from i to j, but
			without "i," at the beginning, so we must add it
		"""
		
		for i,row in enumerate(connections):
			for j,paths in enumerate(row):
				out = '('
				for path in paths:
					out += str(path) + ", "
				out = out[:-2] + ')'
				print "{0},{1}: {2}".format(i,j,out)
	
	def layOut(self, postObjects=None, pocketObjects=None):
		"""Reorient posts with pocket info to world coordinates
		
		Creates: Recreates pocket geometry at origin for all posts in structure
		"""
		
		offset = 0
		
		#set defaults
		if postObjects == None:
			postObjects = ['axis', 'label', 'profile']
		if pocketObjects == None:
			pocketObjects = ['toolpath', 'holes']
		
		for key in self.posts:
			post = self.posts[key]
			
			if post.isConnected:
				transform = copy(post.globalToSelf)
				#add offset into transformation
				transform.M13 += offset
				
				#start list of objects to be transformed with basic post geometry
				guids = post.display(postObjects)
				
				for pocket in post.pockets:
					#transform geometry for each pocket
					#objects.append(sc.doc.Objects.AddSurface(pocket.face))
					guids.extend(pocket.display(pocketObjects))
				for i in reversed(range(len(guids))):
					if type(guids[i]) != System.Guid:
						print "Removed one item of type: {0}\n".format(type(guids[i]))
						del guids[i]
				
				rs.TransformObjects(guids, transform)
				
				offset += 8*common.settings.main['globalScale']
		
	def writeGcode(self):
		"""Organize writing gcode for all posts to files"""
		
		for key in self.posts:
			post = self.posts[key]
			
			gcode = common.Gcode()
			
			f = open('gcode/{0}.nc'.format(post.printId()), 'w')
			
			post.makeGcode(gcode=gcode)
			
			f.write("%\n")
			f.write(gcode.text)
			f.write("\n%")
			
			f.close()
		
	def addPost(self, post):
		"""Add a Post to this Structure and give it an id if necessary"""
		
		if post.id == None:
			raise NameError("Posts without named ids aren't currently supported!")
			#post.id = self.dim
			#self.dim += 1

		self.posts[post.id] = post
				
# End Structure Class #
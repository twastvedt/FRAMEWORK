"""
Joint Class
for lap_joint script

Joint:
	.id             int             Joint identifier
	.posts          list            list of 2 posts at joint
	.pockets        list            list of 2 pockets at joint
	.intersection   list            list of closest points on post axes
	.separation     float           distance between two post axes
	.axis           Line            unit vector starting at .intersection[0] 
										pointing towards .intersection[1]
	.intersecting   Bool            Post axes are actually intersecting
	.face           PlaneSurface    sheared surface common to both Pockets
	.skew           float           angle (radians) of skew between posts (90 = orthogonal)
	.skewFactor     float           d*skewFactor = distance in skewed UV coordinates
"""

import Rhino
import scriptcontext as sc
import rhinoscriptsyntax as rs

import common
from pocket import *


class Joint:
	"""A connection between two Posts."""
	
	def __init__(self, p0, p1, id = None, pocketClass=Pocket):
		"""Initialize a Joint object"""
		
		self.posts = [p0, p1]
		
		self.id = id
		
		self.intersection = common.findClosestPoints(p0.axis, p1.axis)
		
		if rs.Distance(*self.intersection) <= sc.doc.PageAbsoluteTolerance:
			#lines actually intersect. axis is normal to both input lines
			self.intersecting = True
			self.axis = rs.VectorCrossProduct(p0.axis.UnitTangent, p1.axis.UnitTangent)
		else:
			self.intersecting = False
			self.axis = rs.VectorUnitize(Rhino.Geometry.Vector3d(self.intersection[1] 
				- self.intersection[0]))
				
		#store distance between post axes
		self.separation = rs.Distance(*self.intersection)
		
		#orientation is plane at origin, normal along self.axis, x axis along p0
		#start (arbitrarily) at p0's closest point
		self.orientation = rs.PlaneFromNormal(self.intersection[0], self.axis,
			self.posts[0].axis.UnitTangent)
		#origin is midpoint between furthest protrusions of posts, along joint axis
		self.origin = self.getOrigin()
		#move orientation to midpoint of post profiles' bounding box
		self.orientation.Origin = self.origin
		#know how to get back home
		self.selfToGlobal = Rhino.Geometry.Transform.ChangeBasis(self.orientation,
			Rhino.Geometry.Plane.WorldXY)
		
		#initialize pockets
		self.pockets = [pocketClass(p0, 0, self), pocketClass(p1, 1, self)]
		#create sheared surface - starting point for creating pocket toolpaths
		self.face = self.commonFace()

		#create pockets
		for p in self.pockets:
			p.create()
		
	###########
	#Joint Class Functions
	
	def info(self):
		"""Displays a text summary of this Joint."""
		
		print "Joint: " + \
		','.join([p.printId() for p in self.posts]) + \
		"\n Axis: [" + printPoint3d(self.intersection[0]) + ', ' + \
			printPoint3d(self.intersection[1]) + ']' + \
		"\n Origin: " + printPoint3d(self.origin) + \
		"\n----"
	
	def display(self, objects=None):
		"""Create objects in viewport to display information about this Joint
		
		Creates:    label   joint id
					axis    line normal to pocket faces
					origin  center of joint
					face    shared pocket surface
					
		Returns:    list of guids of added objects
		"""
		
		guids = []
		
		if objects == None:
			objects = ['label']
		
		if 'label' in objects:
			guids.append(rs.AddTextDot(self.printId(), self.origin))
		if 'axis' in objects:
			if not self.intersecting:
				guids.append(sc.doc.Objects.AddLine(*self.intersection))
		if 'origin' in objects:
			guids.append(sc.doc.Objects.AddPoint(self.origin))
		if 'face' in objects:
			guids.append(sc.doc.Objects.AddSurface(self.face))
		
		return guids
	
	def printId(self):
		"""return id with type letter"""
		
		return 'j' + str(self.id)
		
	def getOrigin(self):
		"""find joint origin
		
			Returns: Point3d
		"""
		
		p0Bounds, p1Bounds = [self.posts[i].profile.GetBoundingBox(self.orientation) for i in [0,1]]
		
		return self.orientation.PointAt(0,0,(p0Bounds.Max.Z + p1Bounds.Min.Z)/2)
		
	def commonFace(self):
		"""Define the surface of the common pocket face
		
		Returns: sheared surface of pocket
		"""
		
		grid = []
		
		for p in self.pockets:
			pocketToJoint = Rhino.Geometry.Transform.ChangeBasis(p.orientation,
				self.orientation)
			#get width of post
			width = p.profileBounds.Diagonal.Y
			#create lines along x-axis at edges of Post, for intersections
			lines = [Rhino.Geometry.Line(0,y,0, 1,y,0) for y in [-width/2, width/2]]
			
			#transform
			for l in lines:
				l.Transform(pocketToJoint)
				l.FromZ = 0; l.ToZ = 0
			
			grid.append(lines)
			
			#sort by distance from Post's origin
			#xLines.sort(key=lambda line: self.orientation.DistanceTo(line.From))
		
		#build list of corner points
		pairs = [[0,0],[1,0],[1,1],[0,1]]
		corners = [grid[0][c[0]].PointAt(Rhino.Geometry.Intersect.Intersection.LineLine(
			grid[0][c[0]], grid[1][c[1]], 0, False)[1]) for c in pairs]
		#convert corners to global coordinates
		corners = [rs.PointTransform(c, self.selfToGlobal) for c in corners]
		#find angle of skew in pocket
		self.skew = Rhino.Geometry.Vector3d.VectorAngle(
			Rhino.Geometry.Vector3d(corners[1] - corners[0]),
			Rhino.Geometry.Vector3d(corners[3] - corners[0]))
		self.skewFactor = 1/math.sin(self.skew)
		
		#return sheared surface of pocket
		return Rhino.Geometry.NurbsSurface.CreateFromCorners(*corners)
		
# End Joint Class #
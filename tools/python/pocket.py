"""
Pocket Class
for lap_joint script

Pocket:
	.type           string          name of pocket type
	.joint          Joint           corresponding Joint object
	.post           Post            parent Post object
	.index          Integer         currently 0 or 1. index of pocket in list self.joint.pockets
	.origin         Point3D         center of pocket face
	.orientation    Plane           at origin, normal pointing towards other post, 
										x axis aligned to Post's axis
	.profilePlane   Plane           orientation rotated parallel to Post's profile
	.normal         Vector3D        normal of orientation plane
	.rotation       float           rotation of joint off of vertical on oriented post in degrees
	.profileBounds  BoundingBox     Post's end face in pocket's orientation
	.face           NurbsSurface    sheared millable pocket face
	.holes          list            list of bolt hole center Lines
	.toolpath       Toolpath        group of operations for milling this pocket
"""

import Rhino
import scriptcontext as sc
import rhinoscriptsyntax as rs

from copy import copy
import math

import common
from toolpath import *

class Pocket(object):
	"""One half of a joint, cut into a post."""
	
	def __init__(self, post, index, joint):
		"""Gather information about this Pocket."""
		
		#index: Pocket/post number in joint
		self.joint = joint
		self.post = post
		self.post.isConnected = True
		
		self.type = 'default'
		
		post.pockets.append(self)
		#set pocket index so we can find other pockets in this joint
		self.index = index
		
		#joint axis is from p0 to p1
		self.normal = self.joint.axis
		
		if self.index == 1:
			#flip normal line if pocket is on p1
			self.normal = -self.normal
		
		#origin is same as joint's
		self.origin = self.joint.origin
		
		self.orientation = rs.PlaneFromNormal(self.origin, self.normal, post.axis.Direction)
		
		self.profilePlane = rs.RotatePlane(self.orientation, 90, self.orientation.YAxis)
		self.profilePlane.Origin = self.post.origin
		
		#find extents of this post at joint
		self.profileBounds = self.post.profile.GetBoundingBox(self.orientation)
		
		#find rotation of pocket on post in degrees
		self.rotation = common.vectorAngle(self.post.orientation.XAxis, 
			self.normal, self.post.orientation) + 180
			
		#transform from global to rotated post local
		self.globalToMill = self.post.globalToSelf * Rhino.Geometry.Transform.Rotation(-self.rotation * math.pi/180,
			self.post.axis.UnitTangent, self.post.origin)
			
		#transform from rotated post local to global
		t = self.globalToMill.TryGetInverse()
		if t[0]:
			self.millToGlobal = t[1]
		else:
			raise NameError("Couldn't find inverse of rotated post -> global transform")


	###########
	#Pocket Class Functions
	
	def info(self):
		"""Displays a text summary of this Pocket."""
		
		print "Pocket: <{0}> on {1}\nOrigin: {2}\n----".format(
			self.type, self.post.printId(), common.printPoint3d(self.origin))
	
	def display(self, objects=None):
		"""Create objects in viewport to display information about this Joint
		
		Creates:    postLabel   id of other post
					jointLabel  id of joint
					orientation orientation plane
					bounds      bounding box of post's end face
					center      "center" of pocket face
					face        millable pocket face
					farthest    plane on post's farthest edge into joint
					holes       center lines for drill holes
					toolpath    milling path for pocket
					axis        normal of pocket face, at center
					
		Returns:    list of guids of added objects
		"""
		
		guids = []
		
		if objects == None:
			objects = ['holes', 'toolpath']
		
		
		if 'postLabel' in objects:
			guids.append(rs.AddTextDot(self.joint.posts[not self.index].printId(), self.origin))
		if 'jointLabel' in objects:
			guids.append(rs.AddTextDot(self.joint.printId(), self.origin))
		if 'orientation' in objects:
			#display orientation plane
			guids.append(common.displayPlane(self.orientation))
		if 'bounds' in objects:
			#display post profile bounding box
			guids.append(common.displayBoundingBox(self.profileBounds, self.orientation, self.profilePlane))
		if 'center' in objects:
			guids.append(sc.doc.Objects.AddPoint(self.orientation.Origin))
		if 'face' in objects:
			#display pocket face
			guids.append(sc.doc.Objects.AddSurface(self.face))
		if 'holes' in objects:
			#display any drill holes
			for h in self.holes:
				guids.append(sc.doc.Objects.AddLine(h))
		if 'toolpath' in objects:
			#display milling paths
			newguids = self.toolpath.display(transform=self.post.selfToGlobal)
			#print newguids
			guids.extend(newguids)
		if 'axis' in objects:
			#display pocket face normal
			g = sc.doc.Objects.AddLine(self.origin, self.origin + self.normal)
			guids.append(g)
		
		return guids
	
	def UVToPost(self, p, A=0):
		"""change from UV coordinates on skewed pocket face to post's coordinates
			A: additional rotation relative to pocket's rotation
		"""
		
		if A:
			globalToMill = self.post.globalToSelf * \
				Rhino.Geometry.Transform.Rotation(-(self.rotation + A) * math.pi/180,
				self.post.axis.UnitTangent, self.post.origin)
		else:
			globalToMill = self.globalToMill
		
		point = (self.face.PointAt(p.X, p.Y) + self.normal * p.Z)
		point.Transform(globalToMill)
		
		return point
	
	def getBounds(self):
		"""Find the extents of this post at pocket
		
		Returns: bounding box of post profile oriented to pocket orientation
		"""
		
		return self.post.profile.GetBoundingBox(self.orientation)
		
	def create(self):
		"""Finish creating this pocket, once common joint info has been determined"""
		
		#find pocket face boundary
		self.face = self.createPocketFace()
		
		#find bolt hole
		self.holes = self.createHoles()
		
		#create milling path
		self.toolpath = self.makeToolpath()
	
	def createPocketFace(self):
		"""Find pocket face boundary
		
		Returns: millable pocket face
		"""
		
		surface = copy(self.joint.face)
		
		#swap U and V for second Post
		if self.index == 1:
			surface = surface.Transpose()
		
		#extend U edges to allow for endmill to clear post
		surface = surface.Extend(Rhino.Geometry.IsoStatus.West, common.settings.gcode['millDiameter'] * 3, False)
		surface = surface.Extend(Rhino.Geometry.IsoStatus.East, common.settings.gcode['millDiameter'] * 3, False)
		
		#extend V edges for reveal
		if 'reveal' in common.settings.pocket:
			surface = surface.Extend(Rhino.Geometry.IsoStatus.North, common.settings.pocket['reveal'], False)
			surface = surface.Extend(Rhino.Geometry.IsoStatus.South, common.settings.pocket['reveal'], False)
		
		return surface
		
	def createHoles(self):
		"""find center of bolt hole(s)
		This version creates a single hole at the center of the pocket face
		
		Returns: list of center lines starting at pocket face
		"""
		
		#get u,v center of pocket face
		center = [self.joint.face.Domain(a).Mid for a in [0,1]]
		#translate to global
		cPoint = self.joint.face.PointAt(*center)
		#return center line
		return [Rhino.Geometry.Line(cPoint, -self.orientation.Normal, 2)]
		
	def getSection(self, d):
		"""Find bounding box of post geometry above given distance from pocket face
		
		Returns: bounding box containing relevant section of profile
		"""
		
		#construct plane with which to slice profile
		plane = copy(self.orientation)
		#move joint plane 
		plane.Translate(plane.ZAxis * d)
		#intersect with Post profile
		intersections = Rhino.Geometry.Intersect.Intersection.CurvePlane(self.post.profile, plane, 0)
		if intersections:
			#split profile at intersection points
			pieces = self.post.profile.Split([i.ParameterA for i in intersections])
		else:
			pieces = [self.post.profile]
		#initialize bounding box
		bounds = Rhino.Geometry.BoundingBox.Empty
		for p in pieces:
			#get bounding box for each piece of profile curve
			box = p.GetBoundingBox(self.orientation)
			#keep this bounding box if its center is above the plane
			center = box.Center
			#bounding box coordinates are local to the plane where the box was created - convert to global
			center.Transform(Rhino.Geometry.Transform.ChangeBasis(self.orientation, 
				Rhino.Geometry.Plane.WorldXY))
			if plane.DistanceTo(center) > 0:
				#add this bounding box to running total
				bounds.Union(box)
			
		#common.displayBoundingBox(bounds, self.orientation, self.profilePlane)
		return bounds
	
	def getFaceBounds(self, d, uEnds=False, vEnds=False):
		"""Calculate bounds for a face, using default ranges if inputs are False
		
			Returns: (uRange, vRange)
		"""
		
		#zigs
		#find post width at this height, adding room for endmill diameter
		bounds = self.getSection(d)
		
		uPost = Rhino.Geometry.Interval(
			*[self.face.ClosestPoint(self.orientation.PointAt(0,y,0))[1] for y in
			[bounds.Min.Y - 1.5*common.settings.gcode['millDiameter'], 
			bounds.Max.Y + 1.5*common.settings.gcode['millDiameter']]])
		
		if uEnds:
			uRange = list(uEnds)
			
			if uRange[0] is False:
				uRange[0] = uPost.Min
			if uRange[1] is False:
				uRange[1] = uPost.Max
			uRange = Rhino.Geometry.Interval(*uRange)
		else:
			uRange = uPost
		
		#zags
		if vEnds:
			vRange = Rhino.Geometry.Interval(*vEnds)
		else:
			vRange = self.face.Domain(1)
		
		#shrink ranges to account for endmill radius
		UVmillR = common.settings.gcode['millDiameter'] * self.joint.skewFactor / 2
		uRange = Rhino.Geometry.Interval(uRange.Min + UVmillR, uRange.Max - UVmillR)
		vRange = Rhino.Geometry.Interval(vRange.Min + UVmillR, vRange.Max - UVmillR)
		
		return [uRange, vRange]
		
	def facePath(self, d, start=[False, False], uEnds=False, vEnds=False, dir=1):
		"""create minimal zig-zag facing path given distance from pocket face
			start in corner specified by `start`: 
				[0,0] - min U, minV
				[1,1] - max U, max V
			dir: 0 = long moves along same V, 1 = long moves along same U
			Returns: [end corner, list of global points]
		"""
		
		UVmillD = common.settings.gcode['millDiameter'] * self.joint.skewFactor
		
		#get bounds on pocket face for this level
		bounds = self.getFaceBounds(d, uEnds, vEnds)
		uRange = bounds[0]
		vRange = bounds[1]
		
		#start in correct corner
		path = [Rhino.Geometry.Point3d(uRange.Max if start[0] else uRange.Min, 
			vRange.Max if start[1] else vRange.Min, d)]
		
		#switchback in U or V. more concise way to do this?
		if dir:
			#long moves along same U
			
			#direction keeps track of alternating switchback directions (U)
			uDirection = not start[0]
			vDirection = -1 if start[1] else 1
		
			#switchback until we've gone just over the edge in either direction
			while vRange.Min <= path[-1].Y <= vRange.Max:
				path.append(copy(path[-1]))
				#move to other side of pocket
				path[-1].X = uRange.Max if uDirection else uRange.Min
				path.append(copy(path[-1]))
				#step over to next zig
				path[-1].Y += vDirection * common.settings.gcode['stepOver'] * UVmillD
				#reverse direction
				uDirection = not uDirection
			
			#shorten the final zag to be at the edge of the pocket
			path[-1].Y = vRange.Min if start[1] else vRange.Max
			#add a final zig to get the exact pocket width
			path.append(copy(path[-1]))
			path[-1].X = uRange.Max if uDirection else uRange.Min
			
			#change to rotated post's coordinates
			path = [self.UVToPost(p) for p in path]
			
			return [[uDirection, vDirection > 0], path]
		else:
			#long moves along same V
			
			#direction keeps track of alternating switchback directions (U)
			uDirection = -1 if start[0] else 1
			vDirection = not start[1]
			
			#switchback until we've gone just over the edge in either direction
			while uRange.Min <= path[-1].X <= uRange.Max:
				path.append(copy(path[-1]))
				#move to other side of pocket
				path[-1].Y = vRange.Max if vDirection else vRange.Min
				path.append(copy(path[-1]))
				#step over to next zig
				path[-1].X += uDirection * common.settings.gcode['stepOver'] * UVmillD
				#reverse direction
				vDirection = not vDirection
			
			#shorten the final zag to be at the edge of the pocket
			path[-1].X = uRange.Min if start[0] else uRange.Max
			#add a final zig to get the exact pocket width
			path.append(copy(path[-1]))
			path[-1].Y = vRange.Max if vDirection else vRange.Min
			
			#change to rotated post's coordinates
			path = [self.UVToPost(p) for p in path]
			
			return [[uDirection > 0, vDirection], path]
	
	def blockPath(self, startZ, endZ, uEnds=False, vEnds=False, finish=False, dir=1):
		"""Create path to mill a face from startZ to endZ
		uEnds, vEnds: list of endpoints for pocket range in this direction. 
			False uses default value on that end of that direction
		
		Returns: toolpath object
		"""
		
		#start at first cut layer for block, or bottom of pocket if closer
		currentZ = max([startZ - \
			(common.settings.gcode['stepDown'] * common.settings.gcode['millDiameter']),
			endZ])
		
		#create toolpath object
		toolpath = Toolpath()
		
		result = [[False, False], False]
		while True:
			#mill pocket face
			result = self.facePath(currentZ, result[0], uEnds, vEnds, dir=dir)
			toolpath.operations.append(Mill(result[1]))
			#insert rapid move before this mill
			rapid = copy(toolpath.operations[-1].path[0])
			
			toolpath.operations[-1].path.pop(0)
			toolpath.operations.insert(-1, Rapid(rapid, A=None, clear=False))
			
			if currentZ > endZ:
				#at least one more pass - move to next level
				currentZ -= (common.settings.gcode['stepDown'] * common.settings.gcode['millDiameter'])
				if currentZ < endZ:
					#within one layer of pocket face - finish at pocket face
					currentZ = endZ
			else:
				#done!
				break
		
		#clean up pocket edge if needed
		if finish:
			#get bounds on pocket face for this level
			bounds = self.getFaceBounds(currentZ, uEnds, vEnds)
			uRange = bounds[0]
			vRange = bounds[1]
			
			#corner vertices around edge of pocket
			edge = [Rhino.Geometry.Point3d(p[0],p[1],currentZ) for p in [[uRange.Min,
			vRange.Min],[uRange.Max,vRange.Min],[uRange.Max,vRange.Max],[uRange.Min,vRange.Max]]]
			
			#sorry. incomprehensible. This finds the index of the starting vertex in edge
			start = int((1 if result[0][1] else -1) * (result[0][0] + .5) + 1.5)
			
			#rotate edge so that start is at the front
			rotated = edge[start:] + edge[:start]
			#cut along the two sides with ridges from the zigzags
			path = rotated[0:3]
			#change to post's coordinates
			path = [self.UVToPost(p) for p in path]
			
			toolpath.operations.append(Mill(path))
		
		return toolpath
	
	def makeToolpath(self):
		"""Create path to mill this pocket
		
		Returns: Toolpath object
		"""
		
		#start at top of post
		startZ = self.profileBounds.Max.Z
		
		#mill down to pocket face
		toolpath = self.blockPath(startZ, 0)
		
		#add initial rotation
		toolpath.operations[0].A = self.rotation
		#clear post at beginning of pocket
		toolpath.operations[0].clear = True
		
		return toolpath
		
	def makeGcode(self, gcode=False):
		"""Make gcode for this pocket
		
			Returns: gcode string
		"""
		
		gcode.text += "\n(Starting Pocket {0})\n".format(self.joint.printId())
		
		#generate gcode from toolpath
		self.toolpath.makeGcode(gcode=gcode)
		
		return gcode

	# End Pocket Class #



###########
#Pocket Variants

class Pocket_mfBar(Pocket):
	"""One half of a joint, cut into a post.
	Creates a pocket with sliding bar.
		index 0: female - groove perpendicular to post axis
		index 1: male - bar parallel to post axis
	"""
	
	def __init__(self, post, index, joint):
		"""Gather information about this Pocket."""
		
		super(Pocket_mfBar, self).__init__(post, index, joint)
		
		self.type = 'Male/Female Bar'


	###########
	#Pocket_mfBar Class Functions
	
	def display(self, objects=None):
		"""Change defaults from base Pocket class"""
		
		if objects == None:
			objects = ['toolpath']
		
		return super(Pocket_mfBar, self).display(objects)
	
	def create(self):
		"""Finish creating this pocket, once common joint info has been determined"""
		
		#find pocket face boundary
		self.face = self.createPocketFace()
		
		#find pocket holes
		self.holes = self.createHoles()
		
		#create milling path
		self.toolpath = self.makeToolpath()
	
	def makeToolpath(self):
		"""Create path to mill this pocket
			index 0: female - groove perpendicular to post axis
			index 1: male - bar parallel to post axis
		
		Returns: Toolpath object
		"""
		
		#start at top of post
		startZ = self.profileBounds.Max.Z
		
		localOrigin = self.face.ClosestPoint(self.origin)
		
		if self.index == 0:
			#female - groove perpendicular to post axis
			#mill down to top of groove
			toolpath = self.blockPath(startZ, 0)
			#find half of groove width
			offset = (float(common.settings.pocket['barWidth'])/2 + common.settings.pocket['gap']) \
				* round(self.joint.skewFactor,5)
			#create V interval for groove
			grooveRange = [localOrigin[2] - offset, localOrigin[2] + offset]
			#mill groove
			newPath = self.blockPath(0, 
				-common.settings.pocket['barHeight'], vEnds=grooveRange)
			#newPath.operations[0].clear = True
			toolpath.extend(newPath)
			
		else:
			#male - bar parallel to post axis
			#mill down to top of bar
			toolpath = self.blockPath(startZ, common.settings.pocket['barHeight'])
			
			#find half of bar width
			offset = float(common.settings.pocket['barWidth'])/2 * round(self.joint.skewFactor,5)
			#create U interval for bar
			barRange = [localOrigin[1] - offset, localOrigin[1] + offset]
			#mill sides of bar
			newPath = self.blockPath(common.settings.pocket['barHeight'], 0,
				uEnds=[False, barRange[0]], finish=True, dir=0)
			newPath.operations[0].clear = True
			toolpath.extend(newPath)
			
			newPath = self.blockPath(common.settings.pocket['barHeight'], 0, 
				uEnds=[barRange[1], False], finish=True, dir=0)
			newPath.operations[0].clear = True
			toolpath.extend(newPath)
			
			#mark correct location for female post
			"""
			#construct plane with which to slice profile
			plane = copy(self.orientation)
			#move joint plane 
			plane.Translate(plane.ZAxis * common.settings.pocket['barHeight'])
			#intersect with Post profile
			intersections = Rhino.Geometry.Intersect.Intersection.CurvePlane(
				self.joint.posts[not self.index].profile, plane, 0)
			if len(intersections) == 2:
				guides = []
				toLocal = Rhino.Geometry.Transform.ChangeBasis(
					Rhino.Geometry.Plane.WorldXY, self.profilePlane)
				for i in intersections:
					tempPoint = copy(i.PointA)
					tempPoint.Transform(toLocal)
					
					guides.append(Rhino.Geometry.Point3D(-offset - common.settings.gcode['millDiameter'], tempPoint.Y, common.settings.pocket['barHeight'] - common.settings.pocket['guideDepth']))
					guides.append(Rhino.Geometry.Point3D(offset + common.settings.gcode['millDiameter'], tempPoint.Y, common.settings.pocket['barHeight'] - common.settings.pocket['guideDepth']))
					if len(guides) == 2:
						#flip direction of first guide to avoid need for clearance
						guides.reverse()
									
				#change to rotated post's coordinates
				guides = [self.UVToPost(p) for p in guides]
		
				toolpath.operations.extend(guides)
				
			else:
				raise NameError("locating mark didn't find two intersections with other post's profile!")
			"""
		#add initial rotation
		toolpath.operations[0].A = self.rotation
		toolpath.operations[0].clear = True
		
		#add hole mark if wanted
		if common.settings.pocket['markDatum'] > 0:
			toolpath.extend(self.makeHoleToolpath())
		
		return toolpath
		
	def createHoles(self):
		"""find center of bolt hole
		
		Returns: list of center lines from back of post to post axis
		"""
		
		toLocal = Rhino.Geometry.Transform.ChangeBasis(Rhino.Geometry.Plane.WorldXY, self.profilePlane)
		toGlobal = toLocal.TryGetInverse()
		if toGlobal[0]:
			toGlobal = toGlobal[1]
		else:
			raise NameError("Can't invert toLocal transform!")
			return False
		
		#axis line, from post axis, directed away from other post (local)
		#axis = Rhino.Geometry.Line(0,0,0, 0,-12,0)
		
		#axis line, from pocket face center, directed away from other post (local)
		originLocal = copy(self.origin)
		originLocal.Transform(toLocal)
		
		start = Rhino.Geometry.Point3d(originLocal.X, 0, 0)
		
		axis = Rhino.Geometry.Line(start, Rhino.Geometry.Vector3d.XAxis, 12)
		
		#post profile rectangle in profilePlane coordinates
		rectangle = copy(self.post.profile)
		rectangle.Transform(toLocal)
		
		#print axis, rectangle.TryGetPolyline()[1].ToArray()
		intersections = Rhino.Geometry.Intersect.Intersection.CurveCurve(axis.ToNurbsCurve(),
			rectangle, 0, 0)
		if intersections.Count == 1:
			#get intersection distance along axis
			length = intersections[0].PointA.X - originLocal.X
		else:
			raise NameError("Found {0} intersections of axis with post profile".
				format(intersections.Count))
		
		#return center line
		#return [Rhino.Geometry.Line(self.joint.intersection[self.index], -self.orientation.Normal, end)]
		startGlobal = copy(start)
		startGlobal.Transform(toGlobal)
		return [Rhino.Geometry.Line(startGlobal, -self.orientation.Normal, length)]
		
	def makeHoleToolpathV(self):
		"""Create path to mill mark of drill hole in back of post (V shape)
		
			Returns: toolpath
		"""
		
		#Z height of mark on rotated post
		mark = self.holes[0].Length - common.settings.pocket['markDepth']
		
		toolpath = Toolpath()
		
		localOrigin = self.post.globalToSelf * self.origin
		path = [Rhino.Geometry.Point3d(localOrigin.X, 
			common.settings.gcode['clearance'] - mark, 
			common.settings.gcode['clearance']) for x in range(3)]
		
		#move to center, bottom of mark
		path[1].Y = 0; path[1].Z = mark
		#back up to other side
		path[2].Y = -path[2].Y
		
		#rapid to start
		toolpath.operations.append(Rapid(path[0], A=self.rotation - 180, clear=True))
		#rest of path
		toolpath.operations.append(Mill([path[1], path[2]]))
		
		return toolpath
	
	def makeHoleToolpathC(self):
		"""Create path to mill countersink for screw
		
			Returns: toolpath
		"""
		
		#Z height of mark on rotated post
		mark = self.holes[0].Length - common.settings.pocket['markDepth']
		
		radius = common.settings.pocket['csRadius'] - \
			common.settings.gcode['millDiameter'] / 2
		toolpath = Toolpath()
		
		localOrigin = self.post.globalToSelf * self.origin
		start = Rhino.Geometry.Point3d(localOrigin.X, radius, 
			common.settings.gcode['clearance'])
		center = Rhino.Geometry.Point3d(localOrigin.X, 0, mark)
		
		#rapid to start
		toolpath.operations.append(Rapid(start, A=self.rotation - 180, clear=True))
		#circle
		toolpath.operations.append(Arc(center, radius, 0, 360))
		
		return toolpath
	
	
	def makeHoleToolpath(self):
		"""Create path to mill mark for screw
		
			Returns: toolpath
		"""
		
		#Z height of mark on rotated post
		if common.settings.pocket['markDatum'] == 1:
			#distance from post surface
			mark = self.holes[0].Length - common.settings.pocket['markDepth']
		elif common.settings.pocket['markDatum'] == 2:
			#distance from pocket center
			if self.holes[0].Length > common.settings.pocket['markDepth']:
				mark = common.settings.pocket['markDepth']
			else:
				mark = self.holes[0].Length - 0.25
		else:
			raise NameError("Screw mark requested, but unknown datum option specified!")
			return '';
		
		toolpath = Toolpath()
		
		#start of screw axis in skewed pocket face coordinates
		localOrigin = self.face.ClosestPoint(self.origin)
		localOrigin = Rhino.Geometry.Point3d(localOrigin[1],localOrigin[2],0)
		
		if self.index == 0:
			#female - negative offset along male's axis
			localOrigin.X -= common.settings.pocket['holeOffset']
		else:
			#male - offset screw along post's axis
			localOrigin.Y += common.settings.pocket['holeOffset']
			
		localCenter = self.UVToPost(localOrigin, A=180)
		top = Rhino.Geometry.Point3d(localCenter.X, localCenter.Y, 
			common.settings.gcode['clearance'])
		bottom = Rhino.Geometry.Point3d(localCenter.X, localCenter.Y, localCenter.Z + mark)
		
		#rapid to bottom (moves slowly down to z) wouldn't need top, except for non-empty preview line in Rhino
		toolpath.operations.append(Rapid(top, A=self.rotation - 180, clear=True))
		toolpath.operations.append(Mill([top]))
		toolpath.operations.append(Rapid(bottom))
		
		return toolpath
	# End Pocket_mfBar Class #
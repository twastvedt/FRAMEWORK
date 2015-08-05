"""
Post Class
for lap_joint script

Post:
	.id             int         Post identifier
	.brep           Brep        Brep representing Post
	.profile        Curve       Curve defining end profile of post
	.axis           Line        Line between centers of end faces
	.origin         Point       start of axis Line
	.orientation    Plane       plane with normal along axis and x-axis towards 
									center of one face
	.pockets        list        list of Pockets on this Post
	.isConnected    Bool        true if this post is part of a joint
	.selfToGlobal   Transform   convert local coordinates to global
	.globalToSelf   Transform   convert global coordinates to local
	.millToGlobal   Transform   convert unrotated mill coordinates to global
"""

import Rhino
import scriptcontext as sc
import rhinoscriptsyntax as rs

import math

import common
from toolpath import *

class Post:
	"""A single post in the system."""
	
	def __init__(self, axis=None, obRef=None, roll=None, group=None, width=None, height=None, id=None):
		"""Initialize a Post.
		
		Gathers all information about this Post

		Offers multiple ways to describe a Post:
			Start with Rhino object:
				obRef: reference to a Rhino object

			Start with lines:
				group: obRef of one object in a group
				OR
				axis: central axis of the post
				roll: (optional), line normal to axis, defines roll of post

				For a rectangular Post:
					width: width along roll axis
					height: other short dimension of Post
		"""
		
		self.isConnected = False
		self.brep = None
		#not sure about this. id is None until assigned by the Structure?
		self.id = id
		
		if group: #creating Post with axis and roll lines grouped together
			#find group this object belongs to
			groups = group.Object().Attributes.GetGroupList()
			if len(groups) < 1:
				raise NameError("Object does not belong to a group.")
			group_id = groups[0]
			
			#get all objects in the group
			objects = rs.ObjectsByGroup(sc.doc.Groups.GroupName(group_id))
			if len(objects) != 2:
				raise NameError("Group does not have two objects (axis, roll).")
			#get actual curves
			curves = [sc.doc.Objects.Find(ob).CurveGeometry for ob in objects]
			#convert to lines
			lines = [Rhino.Geometry.Line(c.PointAtStart, c.PointAtEnd) for c in curves]
			#roll is shorter than axis
			roll, axis = sorted(lines, key=lambda l: l.Length)
		
		if axis: #creating Post based on lines
			if not (width and height): #currently only rectangular solids.
				raise NameError("Height and width required if an object is not given.")
			
			if type(axis) is Rhino.DocObjects.ObjRef: #axis is objref to a curve
				#find actual curve geometry
				axis = axis.Geometry()
			
			if type(axis) is Rhino.DocObjects.ObjectType.Curve:
				self.axis = Rhino.Geometry.Line(axis.PointAtStart, axis.PointAtEnd)
			else: #assume for now axis is either curve or internal line object
				self.axis = axis
			
			if roll:
				#if roll is a curve, convert it to a Line
				if type(roll) == Rhino.DocObjects.ObjectType.Curve:
					roll = Rhino.Geometry.Line(roll.PointAtStart, roll.PointAtEnd)
					
				self.orientation = rs.PlaneFromNormal(self.axis.From,
					self.axis.UnitTangent, roll.UnitTangent)
				
			else:
				#construct orientation with default roll angle
				self.orientation = rs.PlaneFromNormal(self.axis.From,
				self.axis.UnitTangent)
			
			#construct rectangular profile curve
			self.profile = self.makeRectProfile(width, height)
			
		elif obRef: #no axis, need obRef
			object = obRef.Object()
			if object is None:
				raise NameError("No object found corresponding to reference " + str(obRef))
		
			#actual object geometry
			self.brep = common.getBrep(object)
			
			#assume smallest faces are the ends of the Post
			endFaces = sorted(self.brep.Faces, key=rs.SurfaceArea)[0:2]
			#get curve defining post profile
			self.profile = Rhino.Geometry.Curve.JoinCurves(endFaces[0].DuplicateFace(False).DuplicateEdgeCurves())
			#axis is a Line between centers of smallest faces.
			self.axis = Rhino.Geometry.Line(
				*[rs.SurfaceAreaCentroid(face)[0] for face in endFaces])
		
		else : #no axis and no obRef
			raise NameError('No valid axis or obRef given.')
			
		#just for convenience and simplicity
		self.origin = self.axis.From
		
		#get orientation of Post
		self.orientation = self.findOrientation()
		
		#store conversions to and from Post's orientation
		
		#rotate 90 degrees about y axis to align posts with x instead of z axis
		self.globalToSelf = Rhino.Geometry.Transform.Rotation(1,0,
			Rhino.Geometry.Vector3d.YAxis, Rhino.Geometry.Point3d.Origin)
		#transform global coordinates to post's local coordinates
		self.globalToSelf *= Rhino.Geometry.Transform.ChangeBasis(
			Rhino.Geometry.Plane.WorldXY, self.orientation)
		#go the other way
		self.selfToGlobal = self.globalToSelf.TryGetInverse()[1]
		
		
		#initialize list of this Post's Pockets
		self.pockets = []
		
		
		
		
	###########
	#Post Class Functions
	
	def info(self):
		"""Displays a text summary of this post."""
		
		print "Post: " + self.printId() + \
		"\n Length: " + str(round(self.axis.Length, 2)) + \
		"\n Origin: " + common.printPoint3d(self.origin) + \
		"\n----"
		
	def display(self, objects=None):
		"""Create objects in viewport to display information about this post. 
			'objects' determines which objects to display
		
		Creates:
			label       text dot with post id
			orientation aligned plane with corner on post origin
			profile     profile curve
			object      post object, if not using obrefs
			axis        axis Line
			
		Returns:    list of guids of added objects
		"""
		
		guids = []
		
		if objects == None:
			objects = ['label', 'orientation']
		
		if 'label' in objects:
			guids.append(rs.AddTextDot(self.printId(), self.origin))
		if 'orientation' in objects:
			guids.append(common.displayPlane(self.orientation))
		if 'profile' in objects:
			guids.append(sc.doc.Objects.AddCurve(self.profile))
		if 'object' in objects:
			if not self.brep:
				vector = Rhino.Geometry.Vector3d(self.axis.To - self.axis.From)
				guids.append(sc.doc.Objects.AddBrep(
					Rhino.Geometry.Surface.CreateExtrusion(self.profile, vector).ToBrep()))
				rs.CapPlanarHoles(guids[-1])
		if 'axis' in objects:
			guids.append(sc.doc.Objects.AddLine(self.axis))
		if 'xAxis' in objects:
			guids.append(sc.doc.Objects.AddLine(self.origin, self.origin + self.orientation.XAxis))
		
		return guids
	
	def printId(self):
		"""return id with type letter"""
		
		return 'p' + str(self.id)
	
	def findOrientation(self):
		"""Find the orientation (direction and roll) of a post.
		
		Returns: plane with normal along axis and x-axis towards center of one face.
		
		"""
		
		#grab one edge of profile arbitrarily
		if type(self.profile) is Rhino.Geometry.PolyCurve:
			one_edge = self.profile.Explode()[0]
		else:
			raise NameError("Profile is wrong type of curve: " + str(type(self.profile)))
			
		middle_of_edge = one_edge.PointAtNormalizedLength(.5)
		#create plane from origin, normal vector, and x-axis vector
		return rs.PlaneFromNormal(self.origin,
			self.axis.UnitTangent,
			rs.VectorCreate(self.origin, middle_of_edge))
			
	def makeRoll(self):
		"""Construct a default horizontal roll angle"""
		
		#get plane normal to axis at arbitrary rotation
		plane = rs.PlaneFromNormal(self.axis.From, self.axis.UnitTangent)
		
		#set roll to horizontal component of x axis
		roll = Rhino.Geometry.Vector3d(plane.XAxis.X, plane.XAxis.Y, 0)
		
		if roll.IsZero:
			roll = plane.YAxis
			
		return Rhino.Geometry.Line(self.axis.From, plane.XAxis)
		
	def makeRectProfile(self, width, height):
		"""create a Post profile using the Post's orientation
		
		Returns: rectangular PolyCurve boundary
		"""
		
		#get corner uv coordinates
		corners = [[width/2, height/2], [width/2, -height/2], 
			[-width/2, -height/2], [-width/2, height/2]]
		#close curve
		corners.append(corners[0])
		#convert local uvs to global points
		points = [self.orientation.PointAt(c[0], c[1]) for c in corners]
		#create polylinecurve
		polyline = Rhino.Geometry.Polyline(points)
		#get list of edge curves
		curves = [Rhino.Geometry.LineCurve(line) for line in polyline.GetSegments()]
		#join as polycurve
		return Rhino.Geometry.Curve.JoinCurves(curves)[0]
		
	def makeGcode(self, gcode=False):
		"""Convert mill paths of each pocket into Gcode for the entire Post
		
			Returns: gcode string for milling post
		"""
		
		if not gcode:
			gcode = common.Gcode()
		
		gcode.text += common.settings.gcode['preamble'] + "\n"
		
		gcode.text += "(Starting Post {0})\n".format(self.printId())
		
		for p in self.pockets:
			p.makeGcode(gcode=gcode)
		
		#get coordinates of home point
		home = str(common.settings.gcode['home']).split(',')
		home = [round(float(x), common.settings.gcode['precision']) for x in home]
		#return to home point when finished
		Rapid(Rhino.Geometry.Point3d(*home[0:3]), A=home[3], clear=True).makeGcode(gcode=gcode)
		
		return gcode
		
# End Post Class #
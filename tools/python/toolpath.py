"""
Toolpath Class
for lap_joint script

Toolpath:
	
"""

import Rhino
import scriptcontext as sc
import rhinoscriptsyntax as rs
import System.Guid

from copy import copy
import math

import common


class Toolpath:
	"""Collection of toolpath operations
		
		All toolpath coordinates are local to properly rotated post
		"""
	
	def __init__(self):
		"""Initialize a toolpath group"""
		self.operations = []
	
	def getPath(self, axis=False, 
		transform=False):
		"""Returns: list of points for entire toolpath
			
			transform: global to plane of first orientation
			axis: axis for rotation specified by A values (line)
		"""
		
		axis = axis or Rhino.Geometry.Line(0,0,0, 1,0,0)
		transform = transform or Rhino.Geometry.Transform.Identity
		
		paths = [[]]
		transformBase = copy(transform)
		
		for i, o in enumerate(self.operations):
			newPath = list(o.getPath())
			if o.__class__.__name__ == 'Rapid':
				if o.A:
					
					if len(paths[-1]):
						#apply transformation and move to next path
						paths[-1] = transform.TransformList(paths[-1])
						paths.append([])
					
					#rotate coordinates and start new path
					transform = transformBase * Rhino.Geometry.Transform.Rotation(o.A * math.pi/180,
						axis.UnitTangent, axis.From)
					
				elif i > 0: #only show move to clearance plane if not also rotating
					#separate X/Y and Z movement during rapid moves 
					clearanceV = Rhino.Geometry.Vector3d.ZAxis * common.settings.gcode['clearance']
					
					if o.clear:
						#move up to clearance plan from last location
						paths[-1].append(copy(paths[-1][-1]))
						paths[-1][-1].Z = common.settings.gcode['clearance']
					
					
						
					#move in X and Y first on rapid move
					newPath.append(copy(newPath[-1]))
					newPath[0].Z = paths[-1][-1].Z
				
			paths[-1].extend(newPath)
		
		paths[-1] = transform.TransformList(paths[-1])
		return paths
	
	def extend(self, other):
		"""concatenate two toolpath objects"""
		
		self.operations.extend(other.operations)
		
		return True
	
	def display(self, transform=False, axis=False):
		"""Add a polyline to the document showing toolpath line
		
		Returns: guid for added polyline
		"""
		
		objects = []
		
		for p in self.getPath(transform=transform, axis=axis):
			p = Rhino.Geometry.Polyline(p)
			p.DeleteShortSegments(0.01)
			
			guid = sc.doc.Objects.AddPolyline(p)
			if guid == System.Guid.Empty:
				print "Error adding polyline {0}\nCoordinates:".format(guid)
				for c in p:
					print common.printPoint3d(c)
				print "\n"
			objects.append(guid)
		
		return objects
	
	def makeGcode(self, transform=Rhino.Geometry.Transform.Identity, gcode=False):
		"""create Gcode for this Toolpath group after applying `transform`
		
			Returns: Gcode string
		"""
		
		for o in self.operations:
			o.makeGcode(transform=transform, gcode=gcode)
		
		return gcode
	
class Mill:
	"""cutting operation"""
	
	def __init__(self, path=False):
		"""Initialize a Mill path"""
		
		if path:
			self.path = path
		else:
			self.path = []
		
	def getPath(self, transform=Rhino.Geometry.Transform.Identity):
		return transform.TransformList(self.path)
	
	def info(self):
		"""print info about this Mill path"""
		
		print "Mill"
		return True
	
	def display(self, transform):
		"""add mill path to document as polyline
		
		Returns: guid for added polyline
		"""
		
		return sc.doc.Objects.AddPolyline(transform.TransformList(self.path))
	
	def makeGcode(self, transform=Rhino.Geometry.Transform.Identity, gcode=False):
		"""create Gcode for a Mill path after applying `transform`
		
			Returns: Gcode string
		"""
		
		points = self.getPath(transform)
		
		#desired feedrate for this move
		newFR = round(common.settings.gcode['feedrate'],common.settings.gcode['precision'])
		
		for p in points:
			gcode.text += "X{0} Y{1} Z{2}".format(*[str(round(c, common.settings.gcode['precision']))
				for c in [p.X, p.Y, p.Z]])
			
			#change feedrate if necessary
			if gcode.feedRate != newFR:
				gcode.text += ' F{0}\n'.format(str(newFR))
				gcode.feedRate = newFR
			else:
				gcode.text += "\n"
			
		
		return gcode
		
class Rapid:
	"""move to another location"""
	
	def __init__(self, end, A=None, clear=False):
		"""Initialize a rapid move"""
		
		#target of rapid move
		self.end = end
		self.A = A
		#move to clearance plane first?
		self.clear = clear
	
	def info(self):
		"""print information about this Rapid move"""
		
		text = "Rapid:\n To: ({0},{1},{2})\n".format(str(self.end.X), 
			str(self.end.Y), str(self.end.Z))
		if self.A is not None:
			text += " {0}: {1}\n".format(common.settings.gcode['rotAxis'], str(self.A))
		text += " Clear: {0}\n".format(self.clear)
		
		print text
		return True
	
	def getPath(self, transform=False):
		#return rapid move path, after transform, adding move to clearance plane
		
		#default to identity transform
		transform = transform or Rhino.Geometry.Transform.Identity
		
		return transform.TransformList([self.end])
	
	def display(self, transform):
		"""add target point to document
		
		Returns: guid for added point"""
		
		return sc.doc.Objects.AddPoint(self.end.Transform(transform))
		
	def makeGcode(self, transform=False, gcode=False):
		"""create Gcode for a rapid move after applying `transform`
		
			Returns: Gcode string
		"""
		
		end = self.getPath(transform)[0]
		
		#change to rapid
		gcode.text += "G00 "
		if self.clear:
			gcode.text += "Z{0}\n".format(str(round(common.settings.gcode['clearance'],
				common.settings.gcode['precision'])))
		#rapid move X and Y
		gcode.text += "X{0} Y{1}".format(*[str(round(c, common.settings.gcode['precision']))
			for c in [end.X, end.Y]])
		if self.A is not None:
			#negative because shopbot expects positive rotation to be CW
			gcode.text += " {0}{1}".format(str(common.settings.gcode['rotAxis']),
				str(-round(self.A, common.settings.gcode['precision'])))
		gcode.text += " (Rapid Positioning)\n"
		#slow down to move Z
		gcode.feedRate = round( common.settings.gcode['feedrate'] * 
			common.settings.gcode['approach'],common.settings.gcode['precision'])
		gcode.text += "G01 Z{1} F{0} (Linear Interpolation)\n".format(
			str(gcode.feedRate),
			str(round(end.Z, common.settings.gcode['precision'])))
		
		return gcode


class Arc:
	"""arc cutting operation"""
	
	def __init__(self, center, radius, start, end):
		"""Initialize an arc path, from start to end in degrees
		
			Add ability to specify start point instead of start angle
		"""
		
		self.center = center
		
		if start is not False:
			self.start = start * math.pi / 180
			self.end = end * math.pi / 180
			self.radius = radius
		
		self.circle = Rhino.Geometry.Circle(self.center, self.radius)
		
		self.arc = Rhino.Geometry.ArcCurve(self.circle, self.start, self.end)
	
	def getPath(self, transform=Rhino.Geometry.Transform.Identity):
		#approximate arc with polyline
		polyline = self.arc.ToPolyline(0, 0, 
			maxAngleRadians = math.pi / 2, maxChordLengthRatio = .2, 
			maxAspectRatio = 0, tolerance = 0, minEdgeLength = 0.01, 
			maxEdgeLength = 0.5, keepStartPoint = True)
		
		polyline = polyline.TryGetPolyline()
		if( polyline[0]==False ): 
			return scriptcontext.errorhandler()
		polyline = polyline[1]
		
		#return transformed list of points
		array = polyline.ToArray()
		return transform.TransformList(array)
	
	def info(self):
		"""print info about this Mill path"""
		
		print "Arc:\n Center: ({0}, {1}, {2})\n Degrees: {3}".format(self.center.X,
			self.center.Y, self.center.Z, self.degrees)
		return True
	
	def display(self, transform):
		"""add mill path to document as curve
		
		Returns: guid for added curve
		"""
		
		return sc.doc.Objects.AddCurve(transform * self.arc)
	
	def makeGcode(self, transform=Rhino.Geometry.Transform.Identity, gcode=False):
		"""create Gcode for a Mill path after applying `transform`
		
			Returns: Gcode string
		"""
		
		#desired feedrate for this move
		newFR = round(common.settings.gcode['feedrate'],common.settings.gcode['precision'])
		
		moveToCenter = self.center - self.arc.PointAtStart
		
		gcode.text += "G02 X{0} Y{1} I{2} J{3}".format(*[str(round(c, 
			common.settings.gcode['precision'])) for c in
			[self.arc.PointAtEnd.X, self.arc.PointAtEnd.Y, moveToCenter.X, 
			moveToCenter.Y]])
			
		#change feedrate if necessary
		if gcode.feedRate != newFR:
			gcode.text += ' F{0}\n'.format(str(newFR))
			gcode.feedRate = newFR
		else:
			gcode.text += "\n"
		
		return gcode
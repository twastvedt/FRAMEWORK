"""
Common Functions
for lap_joint script
"""

import Rhino
import scriptcontext as sc
import rhinoscriptsyntax as rs

import ConfigParser
import copy

###########
#Gcode Class

class Gcode:
	"""Holds information about a gcode file"""
	
	def __init__(self):
		"""initialize gcode"""
		
		self.text = ''
		self.feedRate = 0
		self.spindleSpeed = 0


###########
#Settings Class

class Settings:
	"""Holds all global settings and sets defaults. Reads settings from file config"""
	
	def __init__(self):
		"""Read in settings and define defaults"""
		
		config = ConfigParser.ConfigParser(allow_no_value=True)
		config.optionxform = str
		
		config.read('config.cfg')
		
		#main
		self.main = dict(config.items('main'))
		self.parseValues(self.main)
		
		#display
		self.display = dict(config.items('display'))
		self.parseValues(self.display)
		
		#pocket
		self.pocket = dict(config.items('pocket'))
		self.parseValues(self.pocket)
		
		#gcode
		self.gcode = dict(config.items('gcode'))
		self.parseValues(self.gcode)
	
	def parseValues(self, d):
		for key, value in d.iteritems():
			try:
				d[key] = int(value)
			except ValueError:
				try:
					d[key] = float(value)
				except ValueError:
					d[key] = str(value)

###########
#Functions

def displayPlane(plane):
	"""Add an aligned surface to the document centered on plane's origin"""
	
	newPlane = copy.copy(plane)
	newPlane.Origin = newPlane.PointAt(-2,-2)
	rs.AddPlaneSurface(newPlane, 4, 4)
	
def displayBoundingBox(bBox, local, plane=None):
	"""Add boundingbox defined in `local` to document. If 2D, make rectangle on `plane`"""
	
	#define transformation
	transform = Rhino.Geometry.Transform.ChangeBasis(local, Rhino.Geometry.Plane.WorldXY)
	
	if bBox.IsDegenerate(.001):
		#make copies of box corner points
		min = copy.copy(bBox.Min); max = copy.copy(bBox.Max)
		#convert corner points to global coordinates
		min.Transform(transform); max.Transform(transform)
		#create rectangle
		rectangle = Rhino.Geometry.Rectangle3d(plane, min, max)
		sc.doc.Objects.AddCurve(rectangle.ToNurbsCurve())
	else:
		#convert to brep
		brep = bBox.ToBrep()
		#transform to global coordinates
		brep.Transform(transform)
		sc.doc.Objects.AddBrep(brep)

def getObject(name):
	"""Get reference to single Rhino object, checking for failure"""
	
	rc, obRef = Rhino.Input.RhinoGet.GetOneObject("Select " + name, True, Rhino.DocObjects.ObjectType.AnyObject)
	if rc != Rhino.Commands.Result.Success or not obRef : raise NameError(rc)
	return obRef
	
def printPoint3d(p):
	"""format Point for printing"""
	
	return '(' + ', '.join([str(round(c,2)) for c in p]) + ')'

def getBrep(ob):
	"""Retrieve the brep for an object.
	
	Currently only takes into account extrusions.
	
	"""
	
	if ob.Geometry.ObjectType == Rhino.DocObjects.ObjectType.Extrusion :
		#we need to convert extrusions specially
		return ob.Geometry.ToBrep()
	elif ob.Geometry.ObjectType == Rhino.DocObjects.ObjectType.Brep :
		return ob
	else:
		return ob.Brep
	
def findClosestPoints(l0, l1):
		"""Find the location of the shortest line between two lines (usually Post axes)
			**If lines intersect, uses line normal to plane defined by inputs
				arbitrarily picks direction
		
		Returns: list of closest points on l0 and l1
		
		"""
		
		intersection = Rhino.Geometry.Intersect.Intersection.LineLine(l0,
			l1, 0, True)
		
		#start point is on first post's axis
		fromP = l0.PointAt(intersection[1])
		
		#end point is on second post's axis
		toP = l1.PointAt(intersection[2])
		
		return [fromP, toP]

def vectorAngle(vector1, vector2, orientation=Rhino.Geometry.Plane.WorldXY):
	"""find angle between two vectors, order matters
	
		Returns: angle in degrees
	"""
	
	angle = rs.VectorAngle(vector1, vector2)
	if angle is None or abs(angle)<0.001:
		return angle
	cross = rs.VectorCrossProduct(vector1, vector2)
	cross = orientation.RemapToPlaneSpace(orientation.Origin + cross)[1]
	if cross.Z<-0.001:
		return -1.0*angle
	elif cross.Z>0.001:
		return angle
   
	#use XZ plane as backup
	if cross.Y<0:
		return -1.0*angle
	return angle

# End Functions #
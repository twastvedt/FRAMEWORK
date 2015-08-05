# FRAMEWORK
# Barry Beagen, David Moses, Trygve Wastvedt, Robert White
# Python script written by Trygve Wastvedt
# 7/31/2015

import Rhino
import scriptcontext as sc
import rhinoscriptsyntax as rs

# Import related files
from post import *
from pocket import *
from joint import *
from structure import *
from toolpath import *
import common

########
# Main #
########

#initialize
rs.UnselectAllObjects()
common.settings = common.Settings()
structure = Structure()
pocketVariant = [Pocket, Pocket_mfBar][common.settings.pocket['pocketType']]

#select axes representing post centerlines
unnumbered = structure.selectAxes()
#order posts along a line
if unnumbered:
	structure.orderAxes()
#set up data structures
structure.axesToPosts()
#calculate pockets for all intersections
structure.makePockets(pocketVariant)
#print info about structure
structure.info()

for key in structure.posts:
	post = structure.posts[key]
	
	post.display(common.settings.display['post'])
	
	for pocket in post.pockets:
		pocket.display(common.settings.display['pocket'])
	
#structure.posts[0].pockets[0].display(['holes', 'bounds', 'face', 'toolpath'])
	
for joint in structure.joints:
	joint.display(common.settings.display['joint'])
	
structure.layOut(common.settings.display['post-layout'], common.settings.display['pocket-layout'])  
structure.writeGcode()
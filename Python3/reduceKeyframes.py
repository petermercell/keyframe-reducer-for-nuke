# Keyframe Reducer v1.2 by Richard Frazer 
# http://www.richardfrazer.com/tools-tutorials/keyframe-reduction-script-for-nuke/

import nuke
import math
import nukescripts

class doReduceKeyframesPanel(nukescripts.PythonPanel):
    def __init__(self, node):
        # Get reference of tKey knob
        knob_names = nuke.animations()    
        knob_name_with_suffix = knob_names[0]
        knob_name = getKnobName(knob_name_with_suffix)
        k = nuke.thisNode()[knob_name]

        # Default frame range = length of keyframes
        tFirst = first_keyframe_location(k)
        tLast = last_keyframe_location(k)
        
        nukescripts.PythonPanel.__init__(self, 'Reduce keyframes in selected animation?')
        
        # Create knobs
        self.tFrameRange = nuke.String_Knob('tFrameRange', 'Frame Range', f'{tFirst}-{tLast}')
        self.tErrorPercent = nuke.Double_Knob('tErrorPercent', 'Error threshold (%)')
        self.tErrorPercent.setValue(10)
        self.tErrorPercent.setRange(1, 100)
        
        self.pcText = nuke.Text_Knob('%')
        self.pcText.clearFlag(nuke.STARTLINE)
        
        for k in (self.tFrameRange, self.tErrorPercent):
            self.addKnob(k)


def getKnobName(knob_name_with_suffix):
    knob_name = knob_name_with_suffix.split(".")[0]
    return knob_name

def getKnobIndex():
    tclGetAnimIndex = """
    set thisanimation [animations]
    if {[llength $thisanimation] > 1} {
        return "-1"
    } else {
        return [lsearch [in [join [lrange [split [in $thisanimation {animations}] .] 0 end-1] .] {animations}] $thisanimation]
    }
    """
    return int(nuke.tcl(tclGetAnimIndex))


def first_keyframe_location(k):
    first_frames = []
    if k.isAnimated():
        for tOriginalCurve in k.animations():
            tKeys = tOriginalCurve.keys()
            if tKeys:
                first_frames.append(tKeys[0].x)
        print(first_frames)
        return int(min(first_frames))
    else:
        return nuke.root().firstFrame()
    
    
def last_keyframe_location(k):
    last_frames = []
    if k.isAnimated():
        for tOriginalCurve in k.animations():
            tKeys = tOriginalCurve.keys()
            if tKeys:
                last_frames.append(tKeys[-1].x)
        return int(max(last_frames))
    else:
        return nuke.root().lastFrame()
    
def getAngle(deltaH=None, deltaV=None):
    if deltaH:
        angle = math.atan2(deltaV, deltaH)
        if deltaH < 0:
            angle += math.pi
    elif deltaV > 0:
        angle = math.pi / 2
    elif deltaV < 0:
        angle = (3 * math.pi) / 2
    else:
        angle = 0

    return math.degrees(angle)


def doReduceKeyframes():    
    p = doReduceKeyframesPanel(nuke.selectedNode())
        
    if p.showModalDialog():
        undo = nuke.Undo()
        undo.begin("Reduce keyframes")  
                
        tErrorPercent = p.tErrorPercent.value()
        tErrorPercent = max(0.000001, min(tErrorPercent, 100))
        
        tFrameRange = nuke.FrameRange(p.tFrameRange.value())
        tFirstFrame = tFrameRange.first()
        tLastFrame = tFrameRange.last()
        
        knob_names = nuke.animations()
        i = getKnobIndex()
        j = 0
        
        for knob_name_with_suffix in knob_names:
            if i > -1:
                j = i
            
            knob_name = getKnobName(knob_name_with_suffix)
            k = nuke.thisNode()[knob_name]

            if k.isAnimated(j):
                tOriginalCurve = k.animation(j)
                tKeys = tOriginalCurve.keys()
                tOrigFirstFrame = tKeys[0].x
                tOrigLastFrame = tKeys[-1].x
                tOrigKeys = len(tKeys)
                fErrorHeight = getCurveHeight(tOriginalCurve, tFirstFrame, tLastFrame)
                tErrorThreshold = fErrorHeight * (tErrorPercent / 100)

                if tOrigKeys > 2:
                    x = nuke.selectedNode()
                    tempname = f"temp_{knob_name}{j}"
                    tTempKnob = nuke.Double_Knob(tempname)
                    tTempKnob.setAnimated()
                    tTempKnob.setValueAt(tOriginalCurve.evaluate(tFirstFrame), tFirstFrame)
                    tTempKnob.setValueAt(tOriginalCurve.evaluate(tLastFrame), tLastFrame)
                    tTempCurve = tTempKnob.animation(0)

                    if (tFirstFrame > tOrigFirstFrame) or (tLastFrame < tOrigLastFrame):
                        tKeys = x[knob_name].animation(j).keys()
                        tCopyKeys = [tKey for tKey in tKeys if (tKey.x < tFirstFrame or tKey.x > tLastFrame)]
                        tTempKnob.animation(0).addKey(tCopyKeys)
                    
                    deltaH = (tLastFrame - tFirstFrame)
                    deltaV = tTempKnob.getValueAt(tLastFrame) - tTempKnob.getValueAt(tFirstFrame)
                    tMasterSlope = 90 - getAngle(deltaH, deltaV)
                    if tMasterSlope < 0:
                        tMasterSlope += 360

                    if findErrorHeight(tOriginalCurve, tTempCurve, tFirstFrame, tLastFrame, tMasterSlope) < tErrorThreshold:
                        print("Looks like this selection of frames was a straight line. Reduce the error threshold % if it isn't")
                    else:
                        recursion = findGreatestErrorFrame(tOriginalCurve, tFirstFrame, tLastFrame, tErrorThreshold, tTempKnob, tTempCurve, 0)
                    
                    x[knob_name].copyAnimation(j, tTempKnob.animation(0))
                    tFinalKeys = len(x[knob_name].animation(j).keys())
                    tReductionPC = int((float(tFinalKeys) / float(tOrigKeys)) * 100)
                    print(f"{knob_name}[{j}] had {tOrigKeys} keys reduced to {tFinalKeys} keys ({tReductionPC}%)")

            else:
                print(f"No animation found in {knob_name} index {j}")
                
            if i > -1:
                break
            else:
                j += 1

        undo.end()
    

def findGreatestErrorFrame(tOriginalCurve, tFirstFrame, tLastFrame, tErrorThreshold, tTempKnob, tTempCurve, recursion):
    tErrorVal = 0
    tErrorFrame = tFirstFrame
    
    deltaH = tLastFrame - tFirstFrame
    deltaV = tTempKnob.getValueAt(tLastFrame) - tTempKnob.getValueAt(tFirstFrame)
    tMasterSlope = 90 - getAngle(deltaH, deltaV)
    if tMasterSlope < 0:
        tMasterSlope += 360

    for f in range(tFirstFrame, tLastFrame + 1):
        tHypotenuse = tOriginalCurve.evaluate(f) - tTempCurve.evaluate(f)
        tOpposite = math.sin(math.radians(tMasterSlope)) * tHypotenuse
        if abs(tOpposite) > tErrorVal:
            tErrorVal = abs(tOpposite)
            tErrorFrame = f

    v = tOriginalCurve.evaluate(tErrorFrame)
    tTempKnob.setValueAt(v, tErrorFrame)

    firstErrorHeight = findErrorHeight(tOriginalCurve, tTempCurve, tFirstFrame, tErrorFrame, tMasterSlope)
    secondErrorHeight = findErrorHeight(tOriginalCurve, tTempCurve, tErrorFrame, tLastFrame, tMasterSlope)
    
    recursion += 1

    if firstErrorHeight > tErrorThreshold:
        recursion = findGreatestErrorFrame(tOriginalCurve, tFirstFrame, tErrorFrame, tErrorThreshold, tTempKnob, tTempCurve, recursion)
    
    if secondErrorHeight > tErrorThreshold:
        recursion = findGreatestErrorFrame(tOriginalCurve, tErrorFrame, tLastFrame, tErrorThreshold, tTempKnob, tTempCurve, recursion)

    return recursion


def findErrorHeight(tOriginalCurve, tNewCurve, tFirstFrame, tLastFrame, tMasterSlope):
    deltaH = float(tLastFrame - tFirstFrame)
    deltaV = float(tNewCurve.evaluate(tLastFrame) - tNewCurve.evaluate(tFirstFrame))
    tDeltaSlope = 90 - getAngle(deltaH, deltaV)
    tGreatestError = 0

    for f in range(tFirstFrame, tLastFrame + 1):
        tHypotenuse = tOriginalCurve.evaluate(f) - tNewCurve.evaluate(f)
        tDifference = math.sin(math.radians(tDeltaSlope)) * tHypotenuse
        tGreatestError = max(tGreatestError, abs(tDifference))

    return tGreatestError


def getCurveHeight(tOriginalCurve, tFirstFrame, tLastFrame):
    tHighVal = tOriginalCurve.evaluate(tFirstFrame)
    tLowVal = tOriginalCurve.evaluate(tFirstFrame)

    for f in range(tFirstFrame, tLastFrame + 1):
        v = tOriginalCurve.evaluate(f)
        if v < tLowVal:
            tLowVal = v
        if v > tHighVal:
            tHighVal = v
        
    return tHighVal - tLowVal
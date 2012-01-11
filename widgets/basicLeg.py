import beings.core as core
import beings.control as control
import beings.utils as utils
import pymel.core as pm
import maya.cmds as MC

class BasicLeg(core.Widget):
    def __init__(self, part='basicleg', **kwargs):
        super(BasicLeg, self).__init__(part=part, **kwargs)
        #add parentable Nodes
        self.addParentPart('bnd_hip')
        self.addParentPart('bnd_knee')
        self.addParentPart('bnd_ankle')
                    
    def _makeLayout(self, namer):
        """
        build the layout
        """
        toks = ['hip', 'knee', 'ankle', 'ball', 'toe', 'toetip']
        positions = [(0,5,0),
                     (0,2.75,1),
                     (0,.5,0),
                     (0,0,0.5),
                     (0,0,1),
                     (0,0,1.5)]

        legJoints = {}
        legCtls = {}
        pm.select(cl=1)

        #create/register bind joints and layout controls
        for i, tok in enumerate(toks):
            legJoints[tok] = pm.joint(p=positions[i], n = namer.name(r='bnd', d=tok))
            self.registerBindJoint(tok, legJoints[tok])
            legCtls[tok] = control.makeControl(shape='sphere',
                                               scale=[0.3, 0.3, 0.3],
                                               name = namer.name(x='ctl', d=tok, r='layout'))
            self.registerControl(tok, legCtls[tok])
            utils.snap(legJoints[tok], legCtls[tok], orient=False)
            pm.select(legJoints[tok])
            
        for i, tok in enumerate(toks):
            utils.orientJnt(legJoints[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=[1,0,0])            
            legCtls[tok].r.setLocked(True)
        
        ankleCtl = legCtls['ankle']
        for tok in ['ball', 'toe', 'toetip']:
            ctl = legCtls[tok]
            ctl.setParent(ankleCtl)
            ctl.tx.setLocked(True)

        pm.pointConstraint(legCtls['hip'], legJoints['hip'], mo=False)
        pm.pointConstraint(legCtls['knee'], legJoints['knee'], mo=False)
        pm.pointConstraint(legCtls['ankle'], legJoints['ankle'], mo=True)
        #create up-vec locs
        l = pm.spaceLocator(n=namer.name(d='orientor_loc'))
        pm.pointConstraint(legCtls['hip'], legCtls['ankle'], l)
        pm.aimConstraint(legCtls['knee'], l,
                          aimVector=[0,0,1], upVector=[1,0,0],
                          worldUpType='object',
                          worldUpObject = legCtls['hip'])
        l.v.set(0)
        
        #aim the hip at the knee
        pm.aimConstraint(legCtls['knee'], legJoints['hip'], aimVector=[0,1,0],
                         upVector=[1,0,0],
                         worldUpVector=[0,-1,0],
                         worldUpType='objectRotation',
                         worldUpObject=l)
        #aim the knee at the ankle
        pm.aimConstraint(legCtls['ankle'], legJoints['knee'], aimVector=[0,1,0],
                         upVector=[1,0,0],
                         worldUpVector=[0,-1,0],
                         worldUpType='objectRotation',
                         worldUpObject=l)
        #make
        for pr in [('ankle', 'ball'), ('ball', 'toe'), ('toe', 'toetip')]:
            handle = pm.ikHandle(solver='ikSCsolver', sj=legJoints[pr[0]],
                                 ee=legJoints[pr[1]],
                                 n=namer.name(d='%s_ikh' % pr[1]))[0]
            handle.setParent(legCtls[pr[1]])
            pm.makeIdentity(handle)
            handle.v.set(0)
            utils.createStretch(legCtls[pr[0]], legCtls[pr[1]], legJoints[pr[0]], namer)
            #pm.pointConstraint(legCtls[pr[1]], legJoints[pr[1]])            
            
        #make rig controls
        ankleIkCtl = control.makeControl(name=namer.name(d='ankle', r='ik'), shape='jack', color='blue')
        self.registerControl('ankleIK', ankleIkCtl, ctlType='rig')
        utils.snap(legJoints['ankle'], ankleIkCtl, orient=False)
        par = utils.insertNodeAbove(ankleIkCtl)
        pm.pointConstraint(legJoints['ankle'], par, mo=False)

        for tok, jnt in legJoints.items():
            if tok == 'toetip':
                continue
            ctl = pm.createNode('transform', name=namer.name(d=tok, r='fk', x='animctl'))
            utils.snap(jnt, ctl)
            control.makeControl(xform=ctl, shape='cube', color='yellow', scale=[.35, .35, .35])
            self.registerControl(tok, ctl, ctlType='rig')
            
        return namer
    def __setupFkCtls(self, bndJnts, rigCtls, fkToks, scaleDownBone=True):
        """Set up the fk controls.  This will delete the original controls that were passed
        in and rebuild the control shapes on a duplicate of the bind joints
        @return: dict of {tok:ctl}
        """
        fkCtls = utils.dupJntDct(bndJnts, '_bnd_', '_fk_')
        unusedToks = set(fkCtls.keys()).difference(fkToks)
            
        for tok in fkToks:
            newCtl = fkCtls[tok]
            oldCtl = rigCtls[tok]
            ctlArgs = eval(oldCtl.beingsControlInfo.get())
            pm.delete(oldCtl)
            control.makeControl(xform=newCtl, **ctlArgs)
            if scaleDownBone:
                control.scaleDownBone(newCtl)
                
        for tok in unusedToks:            
            ctl = fkCtls.pop(tok)
            if set(ctl.listRelatives()).intersection(fkCtls.values()):
                _logger.warning("Warning - deleting a parent of other controls")
            pm.delete(ctl)
            #also delete the rig ctl
            try:
                pm.delete(rigCtls.pop(tok))
            except KeyError:
                pass
        return fkCtls
    
    def _makeRig(self, namer, bndJnts, rigCtls):
        #add the parenting nodes - this is a required step.  It registers the actual nodes
        #the rig uses to parent widgets to each other
        for tok in ['hip', 'knee', 'ankle']:
            self.setParentNode('bnd_%s' % tok, bndJnts[tok])
        
        o = utils.Orientation()
        side = self.options.getValue('side')
        if side == 'rt':
            o.setAxis('aim', 'negY')
            o.reorientJoints(bndJnts.values())
        fkCtls = self.__setupFkCtls(bndJnts, rigCtls,
                                    ['hip', 'knee', 'ankle', 'ball', 'toe'])
        # fkJnts = utils.dupJntDct(bndJnts, '_bnd_', '_fk_')
        # fkCtls = {}
        # for tok, jnt in fkJnts.items():
        #     if tok == 'toetip':
        #         continue
        #     ctl = control.makeControl(jnt, shape='cube', scale=[.25, .25, .25],
        #                           color='yellow')
        #     control.scaleDownBone(ctl)
        #     fkCtls[tok] = ctl
            
        namer.setTokens(r='ik')
        ikJnts = utils.dupJntDct(bndJnts, '_bnd_', '_ik_')
        ikCtl = rigCtls['ankleIK']
        self.setNodeCateogry(ikCtl, 'ik')
        utils.snap(bndJnts['ankle'], ikCtl, orient=False)
        ikHandle, ikEff = pm.ikHandle(sj=ikJnts['hip'],
                                      ee=ikJnts['ankle'],
                                      solver='ikRPsolver',
                                      n=namer.name(x='ikh'))
        ikHandle.setParent(ikCtl)
        ikCtl.addAttr('fkIk', min=0, max=1, dv=1, k=1)  
        fkIkRev = pm.createNode('reverse', n=namer.name(d='fkik', x='rev'))
        ikCtl.fkIk.connect(fkIkRev.inputX)
        for j in fkCtls.values():
            fkIkRev.outputX.connect(j.v)
            
            
core.WidgetRegistry().register(BasicLeg, "Leg", "A basic IK/FK leg")

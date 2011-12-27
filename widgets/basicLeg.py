import beings.core as core
import beings.control as control
import beings.utils as utils
import pymel.core as pm

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
        for i, tok in enumerate(toks):
            legJoints[tok] = pm.joint(p=positions[i], n = namer.name(r='bnd', d=tok))
            legCtls[tok] = control.makeControl(shape='sphere',
                                               scale=[0.3, 0.3, 0.3],
                                               name = namer.name(x='ctl', d=tok, r='layout'))
            self.registerControl(tok, legCtls[tok])
            utils.snap(legJoints[tok], legCtls[tok], orient=False)
            pm.select(legJoints[tok])
            
        for i, tok in enumerate(toks):
            utils.orientJnt(legJoints[tok], aimVec=[0,1,0], upVec=[1,0,0], worldUpVec=[1,0,0])
            pm.parentConstraint(legCtls[tok], legJoints[tok])
            parent = None
            if i > 0:
                parent = legJoints[toks[i-1]]
            self.registerBindJoint(tok, legJoints[tok])
            legCtls[tok].r.setLocked(True)

        ankleCtl = legCtls['ankle']
        for tok in ['ball', 'toe', 'toetip']:
            ctl = legCtls[tok]
            ctl.setParent(ankleCtl)
            ctl.tx.setLocked(True)

        #make rig controls
        ankleIkCtl = control.makeControl(name=namer.name(d='ankle', r='ik'), shape='sphere', color='blue')
        self.registerControl('ankleIK', ankleIkCtl, ctlType='rig')
        
        #create up-vec locs
        l = pm.spaceLocator(n=namer.name(d='orientor_loc'))
        pm.pointConstraint(legCtls['hip'], legCtls['ankle'], l)
        pm.aimConstraint(legCtls['hip'], l,
                         aimVector=[0,1,0], upVector=[0,0,1],
                         worldUpType='object',
                         worldUpObject = legCtls['knee'])

    def _makeRig(self, namer, bndJnts, rigCtls):
        #add the parenting nodes - this is a required step
        for tok in ['hip', 'knee', 'ankle']:
            self.setParentNode('bnd_%s' % tok, bndJnts[tok])
        
        o = utils.Orientation()
        side = self.options.getOpt('side')
        if side == 'rt':
            o.setAxis('aim', 'negY')
            o.reorientJoints(bndJnts.values())
            
        fkJnts = utils.dupJntDct(bndJnts, '_bnd_', '_fk_')
        fkCtls = {}
        for tok, jnt in fkJnts.items():
            if tok == 'toetip':
                continue
            ctl = control.Control(jnt, shape='cube', scaleToChild=True, scale=[.25, .25, .25],
                                  color='yellow')
            fkCtls[tok] = ctl
        
        pm.delete(fkJnts['toetip'])
        fkJnts.pop('toetip')        
        namer.setTokens(r='ik')
        ikJnts = utils.dupJntDct(bndJnts, '_bnd_', '_ik_')
        ikCtl = control.Control(name=namer.name(), shape='sphere', color='lite blue').xformNode()
        self.setNodeCateogry(ikCtl, 'ik')
        utils.snap(bndJnts['ankle'], ikCtl, orient=False)
        ikHandle, ikEff = pm.ikHandle(sj=ikJnts['hip'], ee=ikJnts['ankle'], solver='ikRPsolver',
                                      n=namer.name(x='ikh'))
        ikHandle.setParent(ikCtl)
        ikCtl.addAttr('fkIk', min=0, max=1, dv=1, k=1)        
        fkIkRev = pm.createNode('reverse', n=namer.name(d='fkik', x='rev'))
        ikCtl.fkIk.connect(fkIkRev.inputX)
        for j in fkJnts.values():
            fkIkRev.outputX.connect(j.v)

core.WidgetRegistry().register(BasicLeg, "Basic Leg", "A basic IK/FK leg")

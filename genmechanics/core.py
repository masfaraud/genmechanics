# -*- coding: utf-8 -*-
"""
Created on Wed Nov 16 11:06:30 2016

@author: steven
"""

import numpy as npy
import networkx as nx
from genmechanics import geometry,tools
from scipy import linalg
from scipy.optimize import fsolve

class ModelError(Exception):
    def __init__(self,message):
        self.message=message

    def __str__(self):
        return 'Model Error: '+self.message

class Part:
    def __init__(self,name=''):
        self.name=name
        
        
class Mechanism:
    def __init__(self,linkages,ground,imposed_speeds,known_static_loads,unknown_static_loads,name=''):
        self.linkages=linkages
        self.ground=ground
        self.name=name
        self.imposed_speeds=imposed_speeds
        self.known_static_loads=known_static_loads
        self.unknown_static_loads=unknown_static_loads
        
        self._utd_kinematic_results=False
        self._utd_static_results=False
        
        
    def _get_parts(self):
        parts=[]
        for linkage in self.linkages:
            for part in [linkage.part1,linkage.part2]:
                if not part in parts:
                    if part!=self.ground:
                        parts.append(part)
        return parts

    parts=property(_get_parts)

    def _get_graph(self):
        G=nx.Graph()
        G.add_nodes_from(self.parts)
        for linkage in self.linkages:
            G.add_node(linkage)
            G.add_edge(linkage,linkage.part1)
            G.add_edge(linkage,linkage.part2)
        return G

    graph=property(_get_graph)

    def _get_holonomic_graph(self):
        G=nx.Graph()
        G.add_nodes_from(self.parts)
        for linkage in self.linkages:
            if linkage.holonomic:
                G.add_node(linkage)
                G.add_edge(linkage,linkage.part1)
                G.add_edge(linkage,linkage.part2)
        return G

    holonomic_graph=property(_get_holonomic_graph)        

    def DrawGraph(self,n_state=None):
        """
        Draw graph with tulip
        """
        import tulip
        import tulipgui
        # Creating tulip graph
        G=tulip.tlp.newGraph()
        nodes={}
        for part in self.parts:
            nodes[part]=G.addNode()
        nodes[self.ground]=G.addNode()
        for linkage in self.linkages:
            nodes[linkage]=G.addNode()          
            for part in [linkage.part1,linkage.part2]:
                G.addEdge(nodes[part],nodes[linkage])

        
        viewLayout = G.getLayoutProperty("viewLayout")
        
        # Apply an FM^3 layout on it
        fm3pParams = tulip.tlp.getDefaultPluginParameters("FM^3 (OGDF)", G)
        fm3pParams["Unit edge length"] = 7
        G.applyLayoutAlgorithm("FM^3 (OGDF)", viewLayout, fm3pParams)

        viewLabel = G.getStringProperty("viewLabel")
        viewColor = G.getColorProperty("viewColor")
        viewShape = G.getIntegerProperty("viewShape")

        for comp,node in nodes.items():
            try:
                viewLabel[node] = comp.name

            except AttributeError:
                viewLabel[node] = comp.__class__.__name__
                viewColor[node]=tulip.tlp.Color.Gray
                viewShape[node]=tulip.tlp.NodeShape.Cube
                
        nodeLinkView = tulipgui.tlpgui.createNodeLinkDiagramView(G)

        raise TypeError

    def DrawPowerGraph(self):
        """
        Draw graph with tulip
        """
        import matplotlib.pyplot as plt

        # Creating tulip graph
        G=nx.Graph()
#        nodes={}
#        edges={}
        widths=[]
        labels={}
        for part in self.parts:
            G.add_node(part)
            
            labels[part]=part.name
#        nodes[self.ground]=G.addNode()
        for linkage in self.linkages:
            G.add_node(linkage)          
            labels[linkage]=linkage.name
#            for part in [linkage.part1,linkage.part2]:
            G.add_edge(linkage,linkage.part1)
            widths.append(abs(self.TransmittedLinkagePower(linkage,0)))
            G.add_edge(linkage,linkage.part2)
            widths.append(abs(self.TransmittedLinkagePower(linkage,1)))
            
        max_widths=max(widths)
        widths=[4*w/max_widths for w in widths]                       
#        edges[linkage,part]=e
        plt.figure()
        pos=nx.spring_layout(G)
        nx.draw_networkx_nodes(G,pos,nodelist=self.linkages,node_color='grey')
        nx.draw_networkx_nodes(G,pos,nodelist=self.parts)
        nx.draw_networkx_labels(G,pos,labels)
        nx.draw_networkx_edges(G,pos,width=widths,edge_color='blue')
        nx.draw_networkx_edges(G,pos)
#        nx.draw_networkx_labels(G,pos,labels)

    def ChangeImposedSpeeds(self,imposed_speeds):
        self.imposed_speeds=imposed_speeds
        self._utd_kinematic_results=False
        self._utd_static_results=False# Change of speeds might change resistant forces: update needed

    def ChangeLoads(self,known_static_loads,unknown_static_loads):
        self.known_static_loads=known_static_loads
        self.unknown_static_loads=unknown_static_loads
        self._utd_static_results=False
        
        
    def Speeds(self,position,part_ref,part):
        """
        Speeds from point belonging to part with part_ref as reference
        """
        q=self.kinematic_vector#force kdof computation
        path=nx.shortest_path(self.holonomic_graph,part_ref,part)
        V=npy.zeros((3,self.n_kdof))
        W=npy.zeros((3,self.n_kdof))
        for il,linkage2 in enumerate(path):
            if not linkage2.__class__.__name__=='Part':
                try:
                    if path[il+1]==linkage2.part2:
                        side=1                            
                    else:
                        side=-1
                except IndexError:
                    # linkage is last element of list
                    if path[il-1]==linkage2.part1:
                        side=1     
                    else:
                        side=-1
                # It's really a linkage
                P=geometry.Euler2TransferMatrix(*linkage2.euler_angles)            
                u=linkage2.position
                uprime=u-position
                L=geometry.CrossProductMatrix(uprime)
                Ve=npy.dot(L,npy.dot(P,linkage2.kinematic_matrix[:3,:]))+npy.dot(P,linkage2.kinematic_matrix[3:,:])
                We=npy.dot(P,linkage2.kinematic_matrix[:3,:])
                for indof,ndof in enumerate(self.kdof[linkage2]):
                    V[:,ndof]+=side*Ve[:,indof] 
                    W[:,ndof]+=side*We[:,indof] 
                
        return npy.hstack((npy.dot(W,q).flatten(),npy.dot(V,q).flatten()))

    
    def LocalLinkageSpeeds(self,linkage):
        """
        :returns: relative speed of linkage in local linkage coordinate system
        """

        try:
            # holonomic linkage
            r=self.kinematic_results[linkage]# results
            vr=npy.array([r[i] for i in range(linkage.n_kinematic_unknowns)])#vector of results
            return npy.dot(linkage.kinematic_matrix,vr).flatten()
        except:
            s=self.Speed(linkage.position,self.ground,linkage.part1)
            v=npy.dot(linkage.P,s[:3])
            w=npy.dot(linkage.P,s[3:])
#            return npy.dot(linkage.P,s)
            return npy.hstack((w,v)).flatten()
    
    def LocalLinkageForces(self,linkage,num_part):
        """
        :returns :Local forces of linkage on part given by its number (0 for part1, 1 for part2)
        """
        r=self.static_results[linkage]# results
        vr=npy.array([r[i] for i in range(linkage.n_static_unknowns)])#vector of results
        if num_part==0:
            return npy.dot(linkage.static_matrix1,vr)
        else:
            return npy.dot(linkage.static_matrix2,vr)

    def GlobalLinkageForces(self,linkage,num_part):
        P=geometry.Euler2TransferMatrix(*linkage.euler_angles)
        lf=self.LocalLinkageForces(linkage,num_part)
        F=npy.zeros(6)
        F[:3]=npy.dot(P,lf[:3])
        F[3:]=npy.dot(P,lf[3:])
        return F
    
    def LocalLoadForces(self,load):
        try:
            F=npy.zeros(6)
            F[:3]=load.forces
            F[3:]=load.torques
            return F
        except AttributeError:       
            r=self.static_results[load]# results
            vr=npy.array([r[i] for i in range(load.n_static_unknowns)])#vector of results
            return npy.dot(load.static_matrix,vr)

    
    def GlobalLoadForces(self,load):
        f=self.LocalLoadForces(load)
#        print(f)
        F=npy.zeros(6)
        F[:3]=npy.dot(load.P,f[:3]).flatten()
#        print(npy.dot(load.P,f[3:]).flatten())
        F[3:]=npy.dot(load.P,f[3:]).flatten()
        return F

    
    def LinkagePowerLosses(self,linkage):
        if linkage.holonomic:
            tf=self.LocalLinkageForces(linkage,0)
            ft=npy.hstack((tf[3:],tf[:3]))
            return npy.dot(self.LocalLinkageSpeeds(linkage),ft)
        else:
            d=self.GlobalLinkageForces(linkage,0)+self.GlobalLinkageForces(linkage,1)
            df=d[:3]
            dt=d[3:]
            s=self.Speeds(linkage.position,self.ground,linkage.part1)
            w=s[:3]
            v=s[3:]
#            print(df,dt,w,v)
            return npy.dot(df,v)+npy.dot(dt,w)

            
    def LoadPower(self,load):
        s=self.Speeds(load.position,self.ground,load.part)
        f=self.GlobalLoadForces(load)
        P=npy.dot(s[3:],f[:3])
        P+=npy.dot(f[3:],s[:3])
        return P
    
    def TransmittedLinkagePower(self,linkage,num_part):
        if num_part==1:
            s=self.Speeds(linkage.position,self.ground,linkage.part2)
        else:
            s=self.Speeds(linkage.position,self.ground,linkage.part1)            
        f=self.GlobalLinkageForces(linkage,num_part)
        P=npy.dot(s[3:],f[:3])
        P+=npy.dot(f[3:],s[:3])
        return P
        
    
    def _get_static_results(self):
        if not self._utd_static_results:
            self._static_results=self._StaticAnalysis()
            self._utd_static_results=True
        return self._static_results

    static_results=property(_get_static_results)
        
    def _get_kinematic_results(self):
        if not self._utd_kinematic_results:
            self._kinematic_results,self._kinematic_vector=self._KinematicAnalysis()
            self._utd_kinematic_results=True
        return self._kinematic_results

    kinematic_results=property(_get_kinematic_results)
    
    def _get_kinematic_vector(self):
        if not self._utd_kinematic_results:
            self._kinematic_results,self._kinematic_vector=self._KinematicAnalysis()
            self._utd_kinematic_results=True
        return self._kinematic_vector

    kinematic_vector=property(_get_kinematic_vector)

        
    def _StaticAnalysis(self):
        # Static parametrisation
        self.sdof={}
        self.n_sdof=0
        kinematic_analysis_required=False
        for linkage in self.linkages:
            self.sdof[linkage]=list(range(self.n_sdof,self.n_sdof+linkage.n_static_unknowns))
            self.n_sdof+=linkage.n_static_unknowns
            if linkage.static_require_kinematic:
                kinematic_analysis_required=True
              
                  
        uloads_parts={}
        for load in self.unknown_static_loads:
            load_unknowns=load.static_matrix.shape[1]
            self.sdof[load]=list(range(self.n_sdof,self.n_sdof+load_unknowns))
            self.n_sdof+=load_unknowns
            if load.static_require_kinematic:
                kinematic_analysis_required=True
            
            # Loading sorting by part
            try:
                uloads_parts[load.part].append(load)
            except:
                uloads_parts[load.part]=[load]

        # Force kinematic computation if required
        if kinematic_analysis_required:
            self.kinematic_results

        # Knowns loads sorting by parts
        loads_parts={}
        for load in self.known_static_loads:
            try:
                loads_parts[load.part].append(load)
            except:
                loads_parts[load.part]=[load]
                
                
        
        lparts=len(self.parts)
        M=npy.zeros((6*lparts,self.n_sdof))
        K=npy.zeros((6*lparts,self.n_sdof))
        F=npy.zeros(6*lparts)
        q=npy.zeros(self.n_sdof)
        nonlinear_eq={}

        # Occurence matrix assembly
        for ip,part in enumerate(self.parts):
            # linkage contribution to the LHS
            for linkage in self.graph[part].keys():
                P=geometry.Euler2TransferMatrix(*linkage.euler_angles)            
                u=linkage.position
                uprime=u
                L=geometry.CrossProductMatrix(uprime)
                if part==linkage.part1:
                    static_matrix=linkage.static_matrix1
                else:
                    static_matrix=linkage.static_matrix2
                    
                Me1=npy.abs(npy.dot(P,static_matrix[:3,:]))>1e-10
                Me2=npy.abs(npy.dot(L,npy.dot(P,static_matrix[:3,:]))+npy.dot(P,static_matrix[3:,:]))>1e-10
                Me=npy.vstack([Me1,Me2])
                for indof,ndof in enumerate(self.sdof[linkage]):
                    M[ip*6:(ip+1)*6,ndof]+=Me[:,indof]

                
                Ke1=npy.dot(P,static_matrix[:3,:])
                Ke2=npy.dot(L,npy.dot(P,static_matrix[:3,:]))+npy.dot(P,static_matrix[3:,:])
                Ke=npy.vstack([Ke1,Ke2])
                for indof,ndof in enumerate(self.sdof[linkage]):
                    K[ip*6:(ip+1)*6,ndof]+=Ke[:,indof]

                    
            # Unknowns loads contribution to the LHS
            try:
                uloads=uloads_parts[part]
            except:
                uloads=[]                
            for load in uloads:
                P=geometry.Euler2TransferMatrix(*load.euler_angles)            
                u=load.position
                uprime=u
                L=geometry.CrossProductMatrix(uprime)
                Me1=npy.abs(npy.dot(P,load.static_matrix[:3,:]))>1e-10
                Me2=npy.abs(npy.dot(L,npy.dot(P,load.static_matrix[:3,:]))+npy.dot(P,load.static_matrix[3:,:]))>1e-10
                Me=npy.vstack([Me1,Me2])
                for indof,ndof in enumerate(self.sdof[load]):
                    M[ip*6:(ip+1)*6,ndof]+=Me[:,indof]
                
                Ke1=npy.dot(P,load.static_matrix[:3,:])
                Ke2=npy.dot(L,npy.dot(P,load.static_matrix[:3,:]))+npy.dot(P,load.static_matrix[3:,:])
                Ke=npy.vstack([Ke1,Ke2])
                for indof,ndof in enumerate(self.sdof[load]):
                    K[ip*6:(ip+1)*6,ndof]=Ke[:,indof]     # minus because of sum is in LHS
                    
                    
            # knowns loads contribution to the RHS
            try:
                loads=loads_parts[part]
            except:
                loads=[]                
            for load in loads:
                P=geometry.Euler2TransferMatrix(*load.euler_angles)            
                u=load.position
                uprime=u
                L=geometry.CrossProductMatrix(uprime)
                F1=npy.dot(P,load.forces)
                F2=npy.dot(L,npy.dot(P,load.forces))+npy.dot(P,load.torques)
                Fe=npy.hstack([F1.reshape(3),F2.reshape(3)])
                F[ip*6:(ip+1)*6]-=Fe # minus because of sum is in LHS
        
        neq=6*lparts
        neq_linear=neq
        indices_r=list(range(neq))
        
        # behavior equations of linkages
        for linkage in self.linkages:
            neq_linkage=linkage.static_behavior_occurence_matrix.shape[0]
            if neq_linkage>0:
                # Adding to occurence matrix
                Me=npy.zeros((neq_linkage,self.n_sdof))
                for indof,ndof in enumerate(self.sdof[linkage]):
                    Me[:,ndof]+=linkage.static_behavior_occurence_matrix[:,indof]    
                M=npy.vstack([M,Me])

                # Adding linear equations to System matrix K
                neq_linear_linkage=linkage.static_behavior_linear_eq.shape[0]
                if neq_linear_linkage>0:
                    Ke=npy.zeros((neq_linear_linkage,self.n_sdof))
                    for indof,ndof in enumerate(self.sdof[linkage]):
                        Ke[neq_linear:neq_linear+6,ndof]+=linkage.static_behavior_linear_eq[:,indof]   
                    K=npy.vstack([K,Ke])
                    indices_r.extend(range(neq_linear,neq_linear+neq_linear_linkage))

                # Collecting non linear equations
#                print(v)
                if linkage.holonomic:
                    if linkage.static_require_kinematic:
                        # Relatives speed in this case
                        ls=self.LocalLinkageSpeeds(linkage)
                        w=ls[:3]
                        v=ls[3:]
                    else:
                        w,v=0,0
                    for i,fct in zip(linkage.static_behavior_nonlinear_eq_indices,linkage.static_behavior_nonlinear_eq):
                        nonlinear_eq[neq+i]=lambda x,v=v,w=w,fct=fct:fct(x,w,v)
                else:
                    if linkage.static_require_kinematic:
                        # Absolute speed in this case in local coordinate system
                        s=self.Speeds(linkage.position,self.ground,linkage.part1)
                        w=npy.dot(linkage.P.T,s[:3])
                        v=npy.dot(linkage.P.T,s[3:])
                    else:
                        w,v=0,0

                    for i,fct in zip(linkage.static_behavior_nonlinear_eq_indices,linkage.static_behavior_nonlinear_eq):
                        nonlinear_eq[neq+i]=lambda x,v=v,w=w,fct=fct:fct(x,w,v)
                        
                # Updating counters
                neq+=neq_linkage
                neq_linear+=neq_linear_linkage
                
                

        # behavior equations of unknowns loads
        for load in self.unknown_static_loads:
            neq_load=load.static_behavior_occurence_matrix.shape[0]
            if neq_load>0:
                # Adding to occurence matrix
                Me=npy.zeros((neq_load,self.n_sdof))
                for indof,ndof in enumerate(self.sdof[load]):
                    Me[:,ndof]+=load.static_behavior_occurence_matrix[:,indof]    
                M=npy.vstack([M,Me])

                # Adding linear equations to System matrix K
                neq_linear_load=load.static_behavior_linear_eq.shape[0]
                if neq_linear_load>0:
                    Ke=npy.zeros((neq_linear_load,self.n_sdof))
                    for indof,ndof in enumerate(self.sdof[load]):
                        Ke[neq_linear:neq_linear+6,ndof]+=load.static_behavior_linear_eq[:,indof]   
                    K=npy.vstack([K,Ke])
                    indices_r.extend(range(neq_linear,neq_linear+neq_linear_load))

                # Collecting non linear equations

                if load.static_require_kinematic:
                    # Absolute speed in this case in local coordinate system
                    s=self.Speeds(load.position,self.ground,load.part)
                    w=npy.dot(load.P.T,s[:3])
                    v=npy.dot(load.P.T,s[3:])
                else:
                    w,v=0,0
                for i,fct in zip(load.static_behavior_nonlinear_eq_indices,load.static_behavior_nonlinear_eq):
                    nonlinear_eq[neq+i]=lambda x,v=v,w=w,fct=fct:fct(x,w,v)
                        
                # Updating counters
                neq+=neq_load
                neq_linear+=neq_linear_load

        
        solvable,solvable_var,resolution_order=tools.EquationsSystemAnalysis(M,None)
#        print(resolution_order)
        if not solvable:
            raise ModelError('Overconstrained system')
        for eqs,variables in resolution_order:
            linear=True
            linear_eqs=[]
            for eq in eqs:
                try:
                    nonlinear_eq[eq]
                    linear=False
                except KeyError:
                    linear_eqs.append(eq)            
            if linear:
                eqs_r=npy.array([indices_r[eq] for eq in eqs])
                other_vars=npy.array([i for i in range(self.n_sdof) if i not in variables])
                Kr=K[eqs_r[:,None],npy.array(variables)]
                Fr=F[eqs_r]-npy.dot(K[eqs_r[:,None],other_vars],q[other_vars])

                q[variables]=linalg.solve(Kr,Fr)
            else:
                nl_eqs=[]
                other_vars=npy.array([i for i in range(self.n_sdof) if i not in variables])
                for eq in eqs:
                    try:
                        f1=nonlinear_eq[eq]
                        vars_func=[i for i in range(self.n_sdof) if M[eq,i]]
                        def f2(x,f1=f1,vars_func=vars_func,variables=variables,q=q):                    
                            x2=[]
                            for variable in vars_func:
                                try:
                                    x2.append(x[variables.index(variable)])
                                except ValueError:
                                    x2.append(q[variable])
                            return f1(x2)
                        nl_eqs.append(f2)
                    except KeyError:
                        # lambdification of linear equations
                        f2=lambda x,indices_r=indices_r,K=K,F=F,eq=eq,q=q,other_vars=other_vars:npy.dot(K[indices_r[eq],variables],x)-F[indices_r[eq]]+npy.dot(K[indices_r[eq],other_vars],q[other_vars])
                        nl_eqs.append(f2)
                f=lambda x:[fi(x) for fi in nl_eqs]
                xs=fsolve(f,npy.zeros(len(variables)))
                if npy.sum(npy.abs(f(xs)))>1e-4:
                    raise ModelError('No convergence of nonlinear phenomena solving'+str(npy.sum(npy.abs(f(xs)))))
                q[variables]=xs


        results={}
        for link,dofs in self.sdof.items():
            rlink={}
            for idof,dof in enumerate(dofs):
                rlink[idof]=q[dof]
            results[link]=rlink
            
        return results        
        
    def _KinematicAnalysis(self):
        # Kinematic setting
        self.n_kdof=0
        self.kdof={}        
        loops=nx.cycle_basis(self.holonomic_graph)
        ll=len(loops)
        ieq=6*ll
        neq=ieq+len(self.imposed_speeds)
        nhl=[]
        for linkage in self.linkages:
            try:
                # Holonomic linkage
                ndofl=linkage.kinematic_matrix.shape[1]
                for dofl in range(ndofl):
                    try:
                        self.kdof[linkage].append(self.n_kdof+dofl)
                    except KeyError:
                        self.kdof[linkage]=[self.n_kdof+dofl]                        
                self.n_kdof+=ndofl
            except AttributeError:
                # Non holonomic linkage
                nhl.append(linkage)
                neq+=len(linkage.kinematic_directions)
                        
        K=npy.zeros((neq,self.n_kdof))
        F=npy.zeros((neq,1))
        q=npy.zeros((self.n_kdof,1))
        M=npy.zeros((neq,self.n_kdof))
        for il,loop in enumerate(loops):
            for ilk,linkage in enumerate(loop):
                if not linkage.__class__.__name__=='Part':
                    try:
                        if loop[ilk+1]==linkage.part2:
                            side=1                            
                        else:
                            side=-1
                    except IndexError:
                        # linkage is last element of list
                        if loop[ilk-1]==linkage.part1:
                            side=1     
                        else:
                            side=-1
                    # Linkage
                    P=geometry.Euler2TransferMatrix(*linkage.euler_angles)            
                    u=linkage.position
                    uprime=u
                    L=geometry.CrossProductMatrix(uprime)
                    Me1=npy.abs(npy.dot(P,linkage.kinematic_matrix[:3,:]))>1e-10
                    Me2=npy.abs(npy.dot(L,npy.dot(P,linkage.kinematic_matrix[:3,:]))+npy.dot(P,linkage.kinematic_matrix[3:,:]))>1e-10
                    Me=npy.vstack([Me1,Me2])
                    for indof,ndof in enumerate(self.kdof[linkage]):
                        M[6*il:6*il+6,ndof]+=Me[:,indof]
                    

                    Ke1=npy.dot(P,linkage.kinematic_matrix[:3,:])
                    Ke2=npy.dot(L,npy.dot(P,linkage.kinematic_matrix[:3,:]))+npy.dot(P,linkage.kinematic_matrix[3:,:])
                    Ke=side*npy.vstack([Ke1,Ke2])
                    for indof,ndof in enumerate(self.kdof[linkage]):
                        K[6*il:6*il+6,ndof]+=Ke[:,indof]
        
        # Non holonomic equations
        for linkage in nhl:
            # Speed computation
            path=nx.shortest_path(self.holonomic_graph,linkage.part1,linkage.part2)
            V=npy.zeros((3,self.n_kdof))
            for il,linkage2 in enumerate(path):
                if not linkage2.__class__.__name__=='Part':
                    try:
                        if path[il+1]==linkage2.part2:
                            side=1                            
                        else:
                            side=-1
                    except IndexError:
                        # linkage is last element of list
                        if path[il-1]==linkage2.part1:
                            side=1     
                        else:
                            side=-1
                    # It's really a linkage
                    P=geometry.Euler2TransferMatrix(*linkage2.euler_angles)            
                    u=linkage2.position
                    uprime=u-linkage.position
                    L=geometry.CrossProductMatrix(uprime)
                    Ve=npy.dot(L,npy.dot(P,linkage2.kinematic_matrix[:3,:]))+npy.dot(P,linkage2.kinematic_matrix[3:,:])
                    for indof,ndof in enumerate(self.kdof[linkage2]):
                        V[:,ndof]+=side*Ve[:,indof]
                        
                    
            P=geometry.Euler2TransferMatrix(*linkage.euler_angles)            
            for direction in linkage.kinematic_directions:
                K[ieq,:]=npy.dot(npy.dot(P,direction),V)
                ieq+=1
        
        # Imposed speeds equations
        for linkage,index,speed in self.imposed_speeds:
            K[ieq,self.kdof[linkage][index]]=1
            F[ieq,0]=speed
            ieq+=1
        
        # deducing M from K for last lines
        M[6*ll:,:]=npy.abs(K[6*ll:,:])>1e-10
        
        solvable,solvable_var,resolution_order=tools.EquationsSystemAnalysis(M,None)
        for eqs,variables in resolution_order:
            eqs=npy.array(eqs)
            other_vars=npy.array([i for i in range(self.n_kdof) if i not in variables])
            Kr=K[eqs[:,None],npy.array(variables)]
            Fr=F[eqs,:]-npy.dot(K[eqs[:,None],other_vars],q[other_vars,:])
            q[variables,:]=linalg.solve(Kr,Fr)
        results={}
        for link,dofs in self.kdof.items():
            rlink={}
            for idof,dof in enumerate(dofs):
                rlink[idof]=q[dof,0]
            results[link]=rlink
        return results,q
    
    def GlobalSankey(self):
        from matplotlib.sankey import Sankey
        flows=[]
        orientations=[]
        labels=[]
        
        
        for load in self.known_static_loads+self.unknown_static_loads:
            flows.append(self.LoadPower(load))
            labels.append(load.name)
            if (load.__class__.__name__=='SimpleUnknownLoad')|(load.__class__.__name__=='KnownLoad'):
                orientations.append(0)
            else:
                orientations.append(-1)
                
        for linkage in self.linkages:
            pl=self.LinkagePowerLosses(linkage)
            if pl!=0:
                flows.append(-pl)
                orientations.append(-1)
                labels.append(linkage.name)
#            pl.append(0.5*l)
        l=max([abs(f) for f in flows])
#        pl=[0.1*l]*len(flows)

        sankey = Sankey(unit='W',scale=1/l)
    
        sankey.add(flows=flows,
           orientations=orientations,labels=labels,)
        
        sankey.finish()
        
    def VMPlot(self,u=1):
        import volmdlr as vm
        points=[]
        for linkage in self.linkages:
            points.append(vm.Point3D(linkage.position))
            points.append(vm.Line3D(vm.Point3D(linkage.position),vm.Point3D(linkage.position+u*linkage.P[:,0])))
        mdl=vm.VolumeModel(points)
        mdl.MPLPlot()
        

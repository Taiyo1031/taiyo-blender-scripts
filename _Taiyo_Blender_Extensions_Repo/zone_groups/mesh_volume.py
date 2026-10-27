"""Cached raw-mesh solid queries in normalized local coordinates (main thread)."""
from collections import defaultdict, deque
import time
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

EPS = 1e-7
DIRECTIONS = tuple(Vector(v).normalized() for v in ((1,.371,.193),(.217,1,.413),(.319,.173,1),(-1,.529,.317),(.619,-1,.227)))

class MeshError(ValueError):
    pass

def triangle_overlap(a, b):
    ea=np.roll(a,-1,axis=0)-a; eb=np.roll(b,-1,axis=0)-b
    na=np.cross(ea[0],ea[1]); nb=np.cross(eb[0],eb[1])
    axes=[na,nb,*[np.cross(x,y) for x in ea for y in eb],
          *[np.cross(na,x) for x in ea],*[np.cross(nb,x) for x in eb]]
    for axis in axes:
        length=np.linalg.norm(axis)
        if length<1e-14: continue
        pa=a@(axis/length); pb=b@(axis/length)
        if pa.max()<pb.min()-1e-10 or pb.max()<pa.min()-1e-10:return False
    return True

class Solid:
    def winding_inside(self, point):
        # Exact solid-angle fallback for rays grazing thin features. This is
        # topology-aware, not a majority vote or a guessed inside/outside result.
        tri=self.vertices[self.triangles]-np.asarray(point)
        a,b,c=tri[:,0],tri[:,1],tri[:,2]
        la=np.linalg.norm(a,axis=1);lb=np.linalg.norm(b,axis=1);lc=np.linalg.norm(c,axis=1)
        numerator=np.einsum('ij,ij->i',a,np.cross(b,c))
        denominator=la*lb*lc+np.einsum('ij,ij->i',a,b)*lc+np.einsum('ij,ij->i',b,c)*la+np.einsum('ij,ij->i',c,a)*lb
        winding=abs(float(np.arctan2(numerator,denominator).sum()/(2*np.pi)))
        if winding<1e-5:return False
        if abs(winding-1)<1e-5:return True
        raise MeshError('Ambiguous mesh boundary; adjust thin or intersecting geometry')

    def contains(self, points):
        points=(np.asarray(points)-self.center)/self.scale
        result=np.zeros(len(points),dtype=bool)
        candidates=np.flatnonzero(np.all(points>=self.lo-EPS,axis=1)&np.all(points<=self.hi+EPS,axis=1))
        for i in candidates:
            p=Vector(points[i]); nearest=self.bvh.find_nearest(p,EPS)
            if nearest[0] is not None: result[i]=True;continue
            votes=[]
            for direction in DIRECTIONS:
                origin=p.copy(); count=0; ambiguous=False
                for _ in range(len(self.triangles)+1):
                    location,normal,index,distance=self.bvh.ray_cast(origin,direction,4.)
                    if location is None:break
                    tri=self.vertices[self.triangles[index]]
                    # A ray through a triangulation edge/vertex is retried.
                    v0,v1=tri[1]-tri[0],tri[2]-tri[0]; v2=np.array(location)-tri[0]
                    d00=v0@v0;d01=v0@v1;d11=v1@v1;d20=v2@v0;d21=v2@v1
                    den=d00*d11-d01*d01
                    u=(d11*d20-d01*d21)/den; v=(d00*d21-d01*d20)/den
                    if min(u,v,1-u-v)<EPS or abs(normal.dot(direction))<EPS:
                        ambiguous=True;break
                    count+=1;origin=location+direction*(EPS*4)
                else: ambiguous=True
                if not ambiguous:
                    votes.append(bool(count%2))
                    if len(votes)>=2:
                        if votes[-1]!=votes[0]: result[i]=self.winding_inside(points[i])
                        else: result[i]=votes[0]
                        break
            else:result[i]=self.winding_inside(points[i])
        return result

def build(mesh, stats):
    """Generator: validation is sliced; Blender triangulation/BVH calls are measured."""
    start=time.perf_counter(); solid=Solid()
    if mesh.is_editmode:raise MeshError('Leave Edit Mode to evaluate Mesh Volume')
    verts=[]
    for i,v in enumerate(mesh.vertices):
        verts.append(tuple(v.co))
        if i%128==0:yield
    if len(verts)<4:raise MeshError('Mesh Volume needs a closed surface')
    verts=np.asarray(verts,dtype=np.float64)
    if not np.all(np.isfinite(verts)):raise MeshError('Non-finite Mesh coordinates')
    lo,hi=verts.min(axis=0),verts.max(axis=0);solid.center=(lo+hi)/2;solid.scale=float(np.max(hi-lo))
    if solid.scale<=1e-12:raise MeshError('Degenerate Mesh Volume')
    solid.vertices=(verts-solid.center)/solid.scale
    edges=defaultdict(list);used=set();faces=[]; vertex_faces=defaultdict(set); vertex_neighbors=defaultdict(lambda:defaultdict(set))
    for i,poly in enumerate(mesh.polygons):
        face=tuple(poly.vertices);faces.append(face);used.update(face)
        if len(set(face))!=len(face):raise MeshError("Repeated vertex in a face")
        for v in face:vertex_faces[v].add(i)
        for a,b in zip(face,face[1:]+face[:1]):edges[tuple(sorted((a,b)))].append((i,a,b))
        if i%128==0:yield
    if len(used)!=len(verts):raise MeshError('Loose vertices are not supported in Mesh Volume')
    adjacency=defaultdict(set)
    for i,entries in enumerate(edges.values()):
        if len(entries)!=2:raise MeshError('Open boundary or non-manifold Mesh Volume')
        a,b=entries
        if a[1:]!=b[:0:-1]:raise MeshError('Inconsistent face winding; recalculate normals')
        adjacency[a[0]].add(b[0]);adjacency[b[0]].add(a[0])
        for v in a[1:]:
            vertex_neighbors[v][a[0]].add(b[0]);vertex_neighbors[v][b[0]].add(a[0])
        if i%128==0:yield
    if len(mesh.edges)!=len(edges):raise MeshError('Loose edges are not supported in Mesh Volume')
    seen={0};todo=deque([0])
    while todo:
        f=todo.popleft()
        for neighbor in adjacency[f]-seen:seen.add(neighbor);todo.append(neighbor)
        if len(seen)%128==0:yield
    if len(seen)!=len(faces):raise MeshError('Use a single connected closed surface')
    for vi,incident in vertex_faces.items():
        visited=set();todo=[next(iter(incident))]
        while todo:
            face=todo.pop()
            if face in visited:continue
            visited.add(face);todo.extend(vertex_neighbors[vi][face]-visited)
        if visited!=incident:raise MeshError('Non-manifold vertex fan')
        if vi%128==0:yield
    native=time.perf_counter();mesh.calc_loop_triangles()
    stats['mesh_native_max_ms']=max(stats.get('mesh_native_max_ms',0),(time.perf_counter()-native)*1000)
    tris=[]
    for i,t in enumerate(mesh.loop_triangles):
        tris.append(tuple(t.vertices))
        if i%128==0:yield
    solid.source_vertices=verts
    solid.source_faces=faces
    solid.source_edges=len(mesh.edges)
    solid.triangles=np.asarray(tris,dtype=np.int32)
    coords=solid.vertices[solid.triangles]
    if np.any(np.linalg.norm(np.cross(coords[:,1]-coords[:,0],coords[:,2]-coords[:,0]),axis=1)<1e-12):raise MeshError('Degenerate triangles in Mesh Volume')
    native=time.perf_counter();solid.bvh=BVHTree.FromPolygons(solid.vertices.tolist(),tris,all_triangles=True,epsilon=0.)
    pairs=solid.bvh.overlap(solid.bvh)
    stats['mesh_native_max_ms']=max(stats.get('mesh_native_max_ms',0),(time.perf_counter()-native)*1000)
    yield
    for n,(i,j) in enumerate(pairs):
        if i>=j:continue
        a,b=coords[i],coords[j]
        shared=set(tris[i])&set(tris[j])
        if shared:
            # Remove legal contact along shared topology; retain crossing interiors.
            a=a+(a.mean(axis=0)-a)*1e-6;b=b+(b.mean(axis=0)-b)*1e-6
        if triangle_overlap(a,b):raise MeshError('Self-intersecting or touching non-adjacent Mesh faces')
        if n%16==0:yield
    solid.lo=solid.vertices.min(axis=0);solid.hi=solid.vertices.max(axis=0)
    stats['mesh_builds']=stats.get('mesh_builds',0)+1
    stats['mesh_build_ms']=stats.get('mesh_build_ms',0)+(time.perf_counter()-start)*1000
    return solid


def unchanged(mesh, solid):
    """Verify raw data after noisy dependency updates without rebuilding BVH."""
    if len(mesh.vertices)!=len(solid.source_vertices) or len(mesh.polygons)!=len(solid.source_faces) or len(mesh.edges)!=solid.source_edges:
        return False
    for i,v in enumerate(mesh.vertices):
        if tuple(v.co)!=tuple(solid.source_vertices[i]):return False
        if i%128==0:yield
    for i,p in enumerate(mesh.polygons):
        if tuple(p.vertices)!=solid.source_faces[i]:return False
        if i%128==0:yield
    return True

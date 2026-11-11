ZONE_KEY = 'ub_zone'
ARCHIVED_KEY = 'ub_archived_from'
CSV_COLUMNS = ('id', 'tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'objname', 'colname')
BUILTIN_PRESET = 'Unreal SM (Default)'
FBX_DEFAULTS = dict(fbx_scale=1.0, fbx_apply_scalings='FBX_SCALE_UNITS',
                    fbx_axis_forward='-Z', fbx_axis_up='Y', fbx_apply_modifiers=True,
                    fbx_smoothing='FACE', fbx_vertex_colors='LINEAR',
                    fbx_triangulate=False, fbx_tangent=False, fbx_apply_transform=False)
FBX_ARGUMENTS = dict(fbx_scale='global_scale', fbx_apply_scalings='apply_scale_options',
                     fbx_axis_forward='axis_forward', fbx_axis_up='axis_up',
                     fbx_apply_modifiers='use_mesh_modifiers', fbx_smoothing='mesh_smooth_type',
                     fbx_vertex_colors='colors_type', fbx_triangulate='use_triangles',
                     fbx_tangent='use_tspace', fbx_apply_transform='bake_space_transform')

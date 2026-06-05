from . import bone_mapper

modules = (
    bone_mapper,
)

def register():
    for mod in modules:
        mod.register()

def unregister():
    for mod in reversed(modules):
        mod.unregister()
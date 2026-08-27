def classFactory(iface):
    from .plugin import OpenBOSPlugin
    return OpenBOSPlugin(iface)

def classFactory(iface):
    from .plugin import OfflineMapGeneratorPlugin
    return OfflineMapGeneratorPlugin(iface)

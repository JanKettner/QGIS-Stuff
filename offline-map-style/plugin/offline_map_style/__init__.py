def classFactory(iface):
    from .plugin import OfflineMapStylePlugin
    return OfflineMapStylePlugin(iface)

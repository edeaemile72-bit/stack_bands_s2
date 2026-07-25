def classFactory(iface):
    from .stack_bands_plugin import StackBandsPlugin
    return StackBandsPlugin(iface)

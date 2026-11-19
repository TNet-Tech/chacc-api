// What the console currently knows. The views render from this.

export const state = {
    info: null,          // /.well-known/chacc
    modules: [],
    graph: null,
    services: null,      // /system/services
    servicesError: null, // 'login' or a message
    filter: '',
    restarting: false,
    loaded: false,
};

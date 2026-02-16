export type SidebarContextProps = {
    state: 'expanded' | 'collapsed';
    open: boolean;
    setOpen: (open: boolean) => void;
    openMobile: boolean;
    setOpenMobile: (open: boolean) => void;
    isMobile: boolean;
    toggleSidebar: () => void;
    sidebarWidth: number;
    setSidebarWidth: (width: number) => void;
    minWidth: number;
    maxWidth: number;
    isResizing: boolean;
    setIsResizing: (isResizing: boolean) => void;
    resizable: boolean;
};

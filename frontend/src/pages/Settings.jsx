import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useSortableTable } from '../lib/useSortableTable';
import { 
    getUsers, createUser, updateUser, updateUserAssignments, deleteUser,
    changePasswordByAdmin, getPasswordResetRequests, dismissPasswordResetRequest,
    getClients, createClient, updateClient, deleteClient,
    getProviders, createProvider, updateProvider, deleteProvider,
    seedDatabase, cleanupRoutesPackages
} from '../lib/api';
import api from '../lib/api';
import { formatDateTime } from '../lib/utils';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Checkbox } from '../components/ui/checkbox';
import {
    Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter,
} from '../components/ui/dialog';
import {
    AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
    AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '../components/ui/alert-dialog';
import { 
    Users, Building2, Truck, Shield, Database, Trash2, Key, Bell,
    Loader2, X, Globe, Settings2,
} from 'lucide-react';
import { toast } from 'sonner';
import { WebhooksTab } from '../components/WebhooksTab';
import { SettingsUsersTab } from '../components/settings/SettingsUsersTab';
import { SettingsClientsTab } from '../components/settings/SettingsClientsTab';
import { SettingsProvidersTab } from '../components/settings/SettingsProvidersTab';
import { SettingsSystemTab } from '../components/settings/SettingsSystemTab';
import { SettingsDriversTab } from '../components/settings/SettingsDriversTab';

const getRoleLabel = (role) => ({ agent: 'Agente', coordinator: 'Coordinador', executive: 'Ejecutivo', developer: 'Developer', proveedor: 'Proveedor' }[role] || role);
const getRoleBadgeColor = (role) => ({ agent: 'bg-emerald-100 text-emerald-700', coordinator: 'bg-blue-100 text-blue-700', executive: 'bg-slate-100 text-slate-700', developer: 'bg-violet-100 text-violet-700', proveedor: 'bg-amber-100 text-amber-700' }[role] || 'bg-slate-100 text-slate-700');

const Settings = () => {
    const { isCoordinator } = useAuth();
    const [activeTab, setActiveTab] = useState('users');
    const [users, setUsers] = useState([]);
    const [clients, setClients] = useState([]);
    const [providers, setProviders] = useState([]);
    const [resetRequests, setResetRequests] = useState([]);
    const [loading, setLoading] = useState(true);
    const [systemConfig, setSystemConfig] = useState(null);
    const [configLoading, setConfigLoading] = useState(false);

    // User modal
    const [showUserModal, setShowUserModal] = useState(false);
    const [editingUser, setEditingUser] = useState(null);
    const [userForm, setUserForm] = useState({ name: '', email: '', role: '', password: '' });
    const [userAssignments, setUserAssignments] = useState({ assigned_clients: [], assigned_providers: [] });
    const [userSubmitting, setUserSubmitting] = useState(false);

    // Assignment modal
    const [showAssignmentModal, setShowAssignmentModal] = useState(false);
    const [assignmentUser, setAssignmentUser] = useState(null);
    const [assignmentSubmitting, setAssignmentSubmitting] = useState(false);

    // Password modal
    const [showPasswordModal, setShowPasswordModal] = useState(false);
    const [passwordUser, setPasswordUser] = useState(null);
    const [newPassword, setNewPassword] = useState('');
    const [passwordSubmitting, setPasswordSubmitting] = useState(false);

    // Delete confirm
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [deleteType, setDeleteType] = useState('');

    // Entity modal
    const [showEntityModal, setShowEntityModal] = useState(false);
    const [entityType, setEntityType] = useState('');
    const [editingEntity, setEditingEntity] = useState(null);
    const [entityForm, setEntityForm] = useState({ name: '', contact_name: '', contact_phone: '' });
    const [entitySubmitting, setEntitySubmitting] = useState(false);

    // Search
    const [searchUsers, setSearchUsers] = useState('');
    const [searchClients, setSearchClients] = useState('');
    const [searchProviders, setSearchProviders] = useState('');

    // Cleanup
    const [showCleanupConfirm, setShowCleanupConfirm] = useState(false);

    // Sortable tables
    const filteredUsers = users.filter(u => !searchUsers || u.name?.toLowerCase().includes(searchUsers.toLowerCase()) || u.email?.toLowerCase().includes(searchUsers.toLowerCase()));
    const { sortedData: sortedUsers, SortHeader: UserSortHeader } = useSortableTable(filteredUsers, 'name', 'asc');
    const filteredClients = clients.filter(c => !searchClients || c.name?.toLowerCase().includes(searchClients.toLowerCase()));
    const { sortedData: sortedClients, SortHeader: ClientSortHeader } = useSortableTable(filteredClients, 'name', 'asc');
    const filteredProviders = providers.filter(p => !searchProviders || p.name?.toLowerCase().includes(searchProviders.toLowerCase()) || p.contact_name?.toLowerCase().includes(searchProviders.toLowerCase()));
    const { sortedData: sortedProviders, SortHeader: ProvSortHeader } = useSortableTable(filteredProviders, 'name', 'asc');

    useEffect(() => { fetchData(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
    useEffect(() => { if (activeTab === 'system') fetchConfig(); }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

    const fetchConfig = async () => {
        setConfigLoading(true);
        try { const res = await api.get('/system/config'); setSystemConfig(res.data); }
        catch (err) { console.error('Error loading system config:', err); }
        finally { setConfigLoading(false); }
    };

    const fetchData = async () => {
        try {
            const [usersRes, clientsRes, providersRes, requestsRes] = await Promise.all([
                getUsers(), getClients(), getProviders(), getPasswordResetRequests(),
            ]);
            setUsers(usersRes.data); setClients(clientsRes.data); setProviders(providersRes.data);
            setResetRequests(requestsRes.data.filter(r => r.status === 'pending'));
        } catch { toast.error('Error al cargar datos'); }
        finally { setLoading(false); }
    };

    // Handlers
    const handleOpenUserModal = (user = null) => {
        setEditingUser(user);
        setUserForm(user ? { name: user.name, email: user.email, role: user.role, password: '' } : { name: '', email: '', role: '', password: '' });
        setShowUserModal(true);
    };

    const handleSaveUser = async () => {
        if (!userForm.name || !userForm.email || !userForm.role) { toast.error('Completa todos los campos requeridos'); return; }
        if (!editingUser && !userForm.password) { toast.error('La contrasena es requerida para nuevos usuarios'); return; }
        setUserSubmitting(true);
        try {
            if (editingUser) { await updateUser(editingUser.id, { name: userForm.name, email: userForm.email, role: userForm.role }); toast.success('Usuario actualizado'); }
            else { await createUser(userForm); toast.success('Usuario creado'); }
            setShowUserModal(false); fetchData();
        } catch (error) { toast.error(error.response?.data?.detail || 'Error al guardar usuario'); }
        finally { setUserSubmitting(false); }
    };

    const handleOpenAssignmentModal = (user) => {
        setAssignmentUser(user);
        setUserAssignments({ assigned_clients: user.assigned_clients || [], assigned_providers: user.assigned_providers || [] });
        setShowAssignmentModal(true);
    };

    const toggleClientAssignment = (clientId) => setUserAssignments(prev => ({
        ...prev, assigned_clients: prev.assigned_clients.includes(clientId) ? prev.assigned_clients.filter(id => id !== clientId) : [...prev.assigned_clients, clientId]
    }));

    const toggleProviderAssignment = (providerId) => setUserAssignments(prev => ({
        ...prev, assigned_providers: prev.assigned_providers.includes(providerId) ? prev.assigned_providers.filter(id => id !== providerId) : [...prev.assigned_providers, providerId]
    }));

    const handleSaveAssignments = async () => {
        setAssignmentSubmitting(true);
        try { await updateUserAssignments(assignmentUser.id, userAssignments); toast.success('Asignaciones actualizadas'); setShowAssignmentModal(false); fetchData(); }
        catch { toast.error('Error al guardar asignaciones'); }
        finally { setAssignmentSubmitting(false); }
    };

    const handleOpenPasswordModal = (user) => { setPasswordUser(user); setNewPassword(''); setShowPasswordModal(true); };

    const handleChangePassword = async () => {
        if (!newPassword || newPassword.length < 6) { toast.error('La contrasena debe tener al menos 6 caracteres'); return; }
        setPasswordSubmitting(true);
        try { await changePasswordByAdmin(passwordUser.id, newPassword); toast.success('Contrasena actualizada'); setShowPasswordModal(false); fetchData(); }
        catch { toast.error('Error al cambiar contrasena'); }
        finally { setPasswordSubmitting(false); }
    };

    const handleDismissRequest = async (requestId) => {
        try { await dismissPasswordResetRequest(requestId); toast.success('Solicitud descartada'); fetchData(); }
        catch { toast.error('Error al descartar solicitud'); }
    };

    const handleOpenEntityModal = (type, entity = null) => {
        setEntityType(type); setEditingEntity(entity);
        setEntityForm(entity ? { name: entity.name || '', contact_name: entity.contact_name || '', contact_phone: entity.contact_phone || '' } : { name: '', contact_name: '', contact_phone: '' });
        setShowEntityModal(true);
    };

    const handleSaveEntity = async () => {
        if (!entityForm.name) { toast.error('El nombre es requerido'); return; }
        setEntitySubmitting(true);
        try {
            if (editingEntity) {
                if (entityType === 'client') { await updateClient(editingEntity.id, { name: entityForm.name }); toast.success('Cliente actualizado'); }
                else { await updateProvider(editingEntity.id, entityForm); toast.success('Proveedor actualizado'); }
            } else {
                if (entityType === 'client') { await createClient({ name: entityForm.name }); toast.success('Cliente creado'); }
                else { await createProvider(entityForm); toast.success('Proveedor creado'); }
            }
            setShowEntityModal(false); setEditingEntity(null); fetchData();
        } catch { toast.error('Error al guardar'); }
        finally { setEntitySubmitting(false); }
    };

    const handleDeleteEntity = (type, id) => { setDeleteTarget({ id, type }); setDeleteType(type === 'client' ? 'cliente' : 'proveedor'); setShowDeleteConfirm(true); };

    const handleConfirmDelete = async () => {
        if (!deleteTarget) return;
        try {
            if (deleteTarget.type === 'user') { await deleteUser(deleteTarget.id); toast.success('Usuario eliminado'); }
            else if (deleteTarget.type === 'client') { await deleteClient(deleteTarget.id); toast.success('Cliente eliminado'); }
            else if (deleteTarget.type === 'provider') { await deleteProvider(deleteTarget.id); toast.success('Proveedor eliminado'); }
            setShowDeleteConfirm(false); setDeleteTarget(null); fetchData();
        } catch (error) { toast.error(error.response?.data?.detail || 'Error al eliminar'); setShowDeleteConfirm(false); }
    };

    const handleSeedDatabase = async () => {
        try { const res = await seedDatabase(); toast.success(res.data.message); fetchData(); }
        catch (error) { toast.error(error.response?.data?.detail || 'Error al inicializar'); }
    };

    const handleCleanupData = async () => {
        setShowCleanupConfirm(false);
        try { const res = await cleanupRoutesPackages(); const d = res.data.deleted; toast.success(`Limpieza completada: ${d.journeys} rutas, ${d.packages} paquetes, ${d.incidents} incidencias eliminadas`); }
        catch { toast.error('Error al limpiar datos'); }
    };

    if (!isCoordinator()) {
        return (
            <div className="text-center py-16">
                <Shield className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-700 mb-2">Acceso restringido</h3>
                <p className="text-slate-500">Solo los coordinadores pueden acceder a la configuracion</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">Configuracion</h1>
                    <p className="text-slate-500 text-sm">Administra usuarios, clientes y proveedores</p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" onClick={handleSeedDatabase} data-testid="seed-btn"><Database className="w-4 h-4 mr-2" />Inicializar datos</Button>
                    <Button variant="outline" className="text-red-600 border-red-200 hover:bg-red-50" onClick={() => setShowCleanupConfirm(true)} data-testid="cleanup-btn"><Trash2 className="w-4 h-4 mr-2" />Limpiar rutas y pedidos</Button>
                </div>
            </div>

            {/* Password Reset Requests Alert */}
            {resetRequests.length > 0 && (
                <Card className="border-amber-200 bg-amber-50">
                    <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                            <Bell className="w-5 h-5 text-amber-600 mt-0.5" />
                            <div className="flex-1">
                                <p className="font-medium text-amber-800">Solicitudes de restablecimiento de contrasena</p>
                                <div className="mt-2 space-y-2">
                                    {resetRequests.map((req) => (
                                        <div key={req.id} className="flex items-center justify-between bg-white p-3 rounded-sm border border-amber-200">
                                            <div>
                                                <p className="font-medium text-slate-900">{req.user_name}</p>
                                                <p className="text-sm text-slate-500">{req.user_email}</p>
                                                <p className="text-xs text-slate-400">{formatDateTime(req.requested_at)}</p>
                                            </div>
                                            <div className="flex gap-2">
                                                <Button size="sm" onClick={() => handleOpenPasswordModal({ id: req.user_id, name: req.user_name })} data-testid={`approve-reset-${req.id}`}><Key className="w-4 h-4 mr-1" />Cambiar contrasena</Button>
                                                <Button size="sm" variant="ghost" onClick={() => handleDismissRequest(req.id)} data-testid={`dismiss-reset-${req.id}`}><X className="w-4 h-4" /></Button>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList className="grid w-full grid-cols-6">
                    <TabsTrigger value="users" data-testid="tab-users"><Users className="w-4 h-4 mr-2" />Usuarios</TabsTrigger>
                    <TabsTrigger value="drivers" data-testid="tab-drivers"><Truck className="w-4 h-4 mr-2" />Drivers</TabsTrigger>
                    <TabsTrigger value="clients" data-testid="tab-clients"><Building2 className="w-4 h-4 mr-2" />Clientes</TabsTrigger>
                    <TabsTrigger value="providers" data-testid="tab-providers"><Truck className="w-4 h-4 mr-2" />Proveedores</TabsTrigger>
                    <TabsTrigger value="system" data-testid="tab-system"><Settings2 className="w-4 h-4 mr-2" />Sistema</TabsTrigger>
                    <TabsTrigger value="webhooks" data-testid="tab-webhooks"><Globe className="w-4 h-4 mr-2" />Webhooks</TabsTrigger>
                </TabsList>

                <TabsContent value="users">
                    <SettingsUsersTab loading={loading} searchUsers={searchUsers} setSearchUsers={setSearchUsers} sortedUsers={sortedUsers} filteredUsers={filteredUsers} UserSortHeader={UserSortHeader} getRoleBadgeColor={getRoleBadgeColor} getRoleLabel={getRoleLabel} handleOpenUserModal={handleOpenUserModal} handleOpenAssignmentModal={handleOpenAssignmentModal} handleOpenPasswordModal={handleOpenPasswordModal} onDeleteUser={(user) => { setDeleteTarget({ id: user.id, type: 'user' }); setDeleteType('usuario'); setShowDeleteConfirm(true); }} />
                </TabsContent>
                <TabsContent value="drivers">
                    <SettingsDriversTab />
                </TabsContent>
                <TabsContent value="clients">
                    <SettingsClientsTab loading={loading} searchClients={searchClients} setSearchClients={setSearchClients} sortedClients={sortedClients} filteredClients={filteredClients} ClientSortHeader={ClientSortHeader} handleOpenEntityModal={handleOpenEntityModal} handleDeleteEntity={handleDeleteEntity} />
                </TabsContent>
                <TabsContent value="providers">
                    <SettingsProvidersTab loading={loading} searchProviders={searchProviders} setSearchProviders={setSearchProviders} sortedProviders={sortedProviders} filteredProviders={filteredProviders} ProvSortHeader={ProvSortHeader} handleOpenEntityModal={handleOpenEntityModal} handleDeleteEntity={handleDeleteEntity} />
                </TabsContent>
                <TabsContent value="system">
                    <SettingsSystemTab systemConfig={systemConfig} configLoading={configLoading} />
                </TabsContent>
                <TabsContent value="webhooks"><WebhooksTab /></TabsContent>
            </Tabs>

            {/* User Modal */}
            <Dialog open={showUserModal} onOpenChange={setShowUserModal}>
                <DialogContent>
                    <DialogHeader><DialogTitle className="font-heading">{editingUser ? 'Editar usuario' : 'Nuevo usuario'}</DialogTitle></DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2"><Label>Nombre *</Label><Input value={userForm.name} onChange={(e) => setUserForm({ ...userForm, name: e.target.value })} placeholder="Juan Perez" data-testid="user-name-input" /></div>
                        <div className="space-y-2"><Label>Correo electronico *</Label><Input type="email" value={userForm.email} onChange={(e) => setUserForm({ ...userForm, email: e.target.value })} placeholder="juan@empresa.com" data-testid="user-email-input" /></div>
                        <div className="space-y-2">
                            <Label>Rol *</Label>
                            <Select value={userForm.role} onValueChange={(v) => setUserForm({ ...userForm, role: v })}>
                                <SelectTrigger data-testid="user-role-select"><SelectValue placeholder="Seleccionar rol" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="agent">Agente</SelectItem>
                                    <SelectItem value="coordinator">Coordinador</SelectItem>
                                    <SelectItem value="executive">Ejecutivo</SelectItem>
                                    <SelectItem value="developer">Developer</SelectItem>
                                    <SelectItem value="proveedor">Proveedor</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        {!editingUser && (<div className="space-y-2"><Label>Contrasena *</Label><Input type="password" value={userForm.password} onChange={(e) => setUserForm({ ...userForm, password: e.target.value })} placeholder="********" data-testid="user-password-input" /></div>)}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowUserModal(false)}>Cancelar</Button>
                        <Button onClick={handleSaveUser} disabled={userSubmitting} data-testid="save-user-btn">{userSubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}{editingUser ? 'Actualizar' : 'Crear'}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Password Modal */}
            <Dialog open={showPasswordModal} onOpenChange={setShowPasswordModal}>
                <DialogContent>
                    <DialogHeader><DialogTitle className="font-heading">Cambiar contrasena</DialogTitle><DialogDescription>Establecer nueva contrasena para {passwordUser?.name}</DialogDescription></DialogHeader>
                    <div className="space-y-4"><div className="space-y-2"><Label>Nueva contrasena</Label><Input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="********" data-testid="new-password-input" /></div></div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowPasswordModal(false)}>Cancelar</Button>
                        <Button onClick={handleChangePassword} disabled={passwordSubmitting} data-testid="change-password-btn">{passwordSubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}Cambiar contrasena</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Entity Modal */}
            <Dialog open={showEntityModal} onOpenChange={setShowEntityModal}>
                <DialogContent>
                    <DialogHeader><DialogTitle className="font-heading">{editingEntity ? 'Editar' : 'Nuevo'} {entityType === 'client' ? 'cliente' : 'proveedor'}</DialogTitle></DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2"><Label>Nombre *</Label><Input value={entityForm.name} onChange={(e) => setEntityForm({ ...entityForm, name: e.target.value })} placeholder={entityType === 'client' ? 'Empresa ABC' : 'Logistica XYZ'} data-testid="entity-name-input" /></div>
                        {entityType === 'provider' && (
                            <>
                                <div className="space-y-2"><Label>Nombre de contacto</Label><Input value={entityForm.contact_name} onChange={(e) => setEntityForm({ ...entityForm, contact_name: e.target.value })} placeholder="Juan Perez" data-testid="entity-contact-input" /></div>
                                <div className="space-y-2"><Label>Telefono de contacto</Label><Input value={entityForm.contact_phone} onChange={(e) => setEntityForm({ ...entityForm, contact_phone: e.target.value })} placeholder="+52 55 1234 5678" data-testid="entity-phone-input" /></div>
                            </>
                        )}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowEntityModal(false)}>Cancelar</Button>
                        <Button onClick={handleSaveEntity} disabled={entitySubmitting} data-testid="save-entity-btn">{entitySubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}{editingEntity ? 'Guardar' : 'Crear'}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Assignment Modal */}
            <Dialog open={showAssignmentModal} onOpenChange={setShowAssignmentModal}>
                <DialogContent className="max-w-lg">
                    <DialogHeader><DialogTitle className="font-heading">Asignaciones de {assignmentUser?.name}</DialogTitle><DialogDescription>Selecciona los clientes y proveedores asignados a este usuario</DialogDescription></DialogHeader>
                    <div className="space-y-6">
                        <div className="space-y-3">
                            <Label className="font-medium">Clientes asignados</Label>
                            {clients.length === 0 ? <p className="text-sm text-slate-500">No hay clientes registrados</p> : (
                                <div className="space-y-2 max-h-40 overflow-y-auto">
                                    {clients.map((client) => (
                                        <div key={client.id} className="flex items-center space-x-3">
                                            <Checkbox id={`assign-client-${client.id}`} checked={userAssignments.assigned_clients.includes(client.id)} onCheckedChange={() => toggleClientAssignment(client.id)} data-testid={`assign-client-${client.id}`} />
                                            <label htmlFor={`assign-client-${client.id}`} className="text-sm text-slate-700 cursor-pointer">{client.name}</label>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                        <div className="space-y-3">
                            <Label className="font-medium">Proveedores asignados</Label>
                            {providers.length === 0 ? <p className="text-sm text-slate-500">No hay proveedores registrados</p> : (
                                <div className="space-y-2 max-h-40 overflow-y-auto">
                                    {providers.map((provider) => (
                                        <div key={provider.id} className="flex items-center space-x-3">
                                            <Checkbox id={`assign-provider-${provider.id}`} checked={userAssignments.assigned_providers.includes(provider.id)} onCheckedChange={() => toggleProviderAssignment(provider.id)} data-testid={`assign-provider-${provider.id}`} />
                                            <label htmlFor={`assign-provider-${provider.id}`} className="text-sm text-slate-700 cursor-pointer">{provider.name}</label>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowAssignmentModal(false)}>Cancelar</Button>
                        <Button onClick={handleSaveAssignments} disabled={assignmentSubmitting} data-testid="save-assignments-btn">{assignmentSubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}Guardar asignaciones</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Delete Confirm */}
            <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
                <AlertDialogContent>
                    <AlertDialogHeader><AlertDialogTitle className="font-heading">Eliminar {deleteType}?</AlertDialogTitle><AlertDialogDescription>Esta accion no se puede deshacer.</AlertDialogDescription></AlertDialogHeader>
                    <AlertDialogFooter><AlertDialogCancel>Cancelar</AlertDialogCancel><AlertDialogAction onClick={handleConfirmDelete} className="bg-red-600 hover:bg-red-700" data-testid="confirm-delete-btn">Eliminar</AlertDialogAction></AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>

            {/* Cleanup Confirm */}
            <AlertDialog open={showCleanupConfirm} onOpenChange={setShowCleanupConfirm}>
                <AlertDialogContent>
                    <AlertDialogHeader><AlertDialogTitle className="font-heading text-red-700">Eliminar todas las rutas y paquetes?</AlertDialogTitle><AlertDialogDescription>Esta accion eliminara permanentemente todas las rutas, paquetes e incidencias de la base de datos. Los usuarios, clientes y proveedores NO se veran afectados. Esta accion no se puede deshacer.</AlertDialogDescription></AlertDialogHeader>
                    <AlertDialogFooter><AlertDialogCancel>Cancelar</AlertDialogCancel><AlertDialogAction onClick={handleCleanupData} className="bg-red-600 hover:bg-red-700" data-testid="confirm-cleanup-btn">Si, eliminar todo</AlertDialogAction></AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
};

export default Settings;

import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { 
    getUsers, 
    createUser, 
    updateUser, 
    updateUserAssignments,
    deleteUser,
    changePasswordByAdmin,
    getPasswordResetRequests,
    dismissPasswordResetRequest,
    getClients,
    createClient,
    getProviders,
    createProvider,
    seedDatabase
} from '../lib/api';
import { formatDateTime } from '../lib/utils';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Checkbox } from '../components/ui/checkbox';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '../components/ui/dialog';
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from '../components/ui/alert-dialog';
import { 
    Users,
    Building2,
    Truck,
    Plus,
    Pencil,
    Trash2,
    Key,
    Bell,
    AlertCircle,
    CheckCircle2,
    Loader2,
    X,
    Database,
    Shield,
    Link as LinkIcon
} from 'lucide-react';
import { toast } from 'sonner';

const Settings = () => {
    const { isCoordinator } = useAuth();
    const [activeTab, setActiveTab] = useState('users');
    
    // Data
    const [users, setUsers] = useState([]);
    const [clients, setClients] = useState([]);
    const [providers, setProviders] = useState([]);
    const [resetRequests, setResetRequests] = useState([]);
    const [loading, setLoading] = useState(true);

    // User modal
    const [showUserModal, setShowUserModal] = useState(false);
    const [editingUser, setEditingUser] = useState(null);
    const [userForm, setUserForm] = useState({
        name: '',
        email: '',
        role: '',
        password: '',
    });
    const [userAssignments, setUserAssignments] = useState({
        assigned_clients: [],
        assigned_providers: []
    });
    const [userSubmitting, setUserSubmitting] = useState(false);

    // Assignment modal
    const [showAssignmentModal, setShowAssignmentModal] = useState(false);
    const [assignmentUser, setAssignmentUser] = useState(null);
    const [assignmentSubmitting, setAssignmentSubmitting] = useState(false);

    // Password change modal
    const [showPasswordModal, setShowPasswordModal] = useState(false);
    const [passwordUser, setPasswordUser] = useState(null);
    const [newPassword, setNewPassword] = useState('');
    const [passwordSubmitting, setPasswordSubmitting] = useState(false);

    // Delete confirm
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState(null);
    const [deleteType, setDeleteType] = useState('');

    // Client/Provider modal
    const [showEntityModal, setShowEntityModal] = useState(false);
    const [entityType, setEntityType] = useState('');
    const [entityForm, setEntityForm] = useState({
        name: '',
        contact_name: '',
        contact_phone: '',
    });
    const [entitySubmitting, setEntitySubmitting] = useState(false);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            const [usersRes, clientsRes, providersRes, requestsRes] = await Promise.all([
                getUsers(),
                getClients(),
                getProviders(),
                getPasswordResetRequests(),
            ]);
            setUsers(usersRes.data);
            setClients(clientsRes.data);
            setProviders(providersRes.data);
            setResetRequests(requestsRes.data.filter(r => r.status === 'pending'));
        } catch (error) {
            toast.error('Error al cargar datos');
        } finally {
            setLoading(false);
        }
    };

    // User handlers
    const handleOpenUserModal = (user = null) => {
        if (user) {
            setEditingUser(user);
            setUserForm({
                name: user.name,
                email: user.email,
                role: user.role,
                password: '',
            });
        } else {
            setEditingUser(null);
            setUserForm({
                name: '',
                email: '',
                role: '',
                password: '',
            });
        }
        setShowUserModal(true);
    };

    const handleSaveUser = async () => {
        if (!userForm.name || !userForm.email || !userForm.role) {
            toast.error('Completa todos los campos requeridos');
            return;
        }

        if (!editingUser && !userForm.password) {
            toast.error('La contraseña es requerida para nuevos usuarios');
            return;
        }

        setUserSubmitting(true);
        try {
            if (editingUser) {
                await updateUser(editingUser.id, {
                    name: userForm.name,
                    email: userForm.email,
                    role: userForm.role,
                });
                toast.success('Usuario actualizado');
            } else {
                await createUser(userForm);
                toast.success('Usuario creado');
            }
            setShowUserModal(false);
            fetchData();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Error al guardar usuario');
        } finally {
            setUserSubmitting(false);
        }
    };

    const handleDeleteUser = async () => {
        setShowDeleteConfirm(false);
        try {
            await deleteUser(deleteTarget.id);
            toast.success('Usuario eliminado');
            fetchData();
        } catch (error) {
            toast.error('Error al eliminar usuario');
        }
    };

    // Assignment handlers
    const handleOpenAssignmentModal = (user) => {
        setAssignmentUser(user);
        setUserAssignments({
            assigned_clients: user.assigned_clients || [],
            assigned_providers: user.assigned_providers || []
        });
        setShowAssignmentModal(true);
    };

    const toggleClientAssignment = (clientId) => {
        setUserAssignments(prev => ({
            ...prev,
            assigned_clients: prev.assigned_clients.includes(clientId)
                ? prev.assigned_clients.filter(id => id !== clientId)
                : [...prev.assigned_clients, clientId]
        }));
    };

    const toggleProviderAssignment = (providerId) => {
        setUserAssignments(prev => ({
            ...prev,
            assigned_providers: prev.assigned_providers.includes(providerId)
                ? prev.assigned_providers.filter(id => id !== providerId)
                : [...prev.assigned_providers, providerId]
        }));
    };

    const handleSaveAssignments = async () => {
        setAssignmentSubmitting(true);
        try {
            await updateUserAssignments(assignmentUser.id, userAssignments);
            toast.success('Asignaciones actualizadas');
            setShowAssignmentModal(false);
            fetchData();
        } catch (error) {
            toast.error('Error al guardar asignaciones');
        } finally {
            setAssignmentSubmitting(false);
        }
    };

    // Password handlers
    const handleOpenPasswordModal = (user) => {
        setPasswordUser(user);
        setNewPassword('');
        setShowPasswordModal(true);
    };

    const handleChangePassword = async () => {
        if (!newPassword || newPassword.length < 6) {
            toast.error('La contraseña debe tener al menos 6 caracteres');
            return;
        }

        setPasswordSubmitting(true);
        try {
            await changePasswordByAdmin(passwordUser.id, newPassword);
            toast.success('Contraseña actualizada');
            setShowPasswordModal(false);
            fetchData(); // Refresh to update reset requests
        } catch (error) {
            toast.error('Error al cambiar contraseña');
        } finally {
            setPasswordSubmitting(false);
        }
    };

    const handleDismissRequest = async (requestId) => {
        try {
            await dismissPasswordResetRequest(requestId);
            toast.success('Solicitud descartada');
            fetchData();
        } catch (error) {
            toast.error('Error al descartar solicitud');
        }
    };

    // Entity handlers
    const handleOpenEntityModal = (type) => {
        setEntityType(type);
        setEntityForm({
            name: '',
            contact_name: '',
            contact_phone: '',
        });
        setShowEntityModal(true);
    };

    const handleSaveEntity = async () => {
        if (!entityForm.name) {
            toast.error('El nombre es requerido');
            return;
        }

        setEntitySubmitting(true);
        try {
            if (entityType === 'client') {
                await createClient({ name: entityForm.name });
                toast.success('Cliente creado');
            } else {
                await createProvider(entityForm);
                toast.success('Proveedor creado');
            }
            setShowEntityModal(false);
            fetchData();
        } catch (error) {
            toast.error('Error al guardar');
        } finally {
            setEntitySubmitting(false);
        }
    };

    // Seed handler
    const handleSeedDatabase = async () => {
        try {
            const res = await seedDatabase();
            toast.success(res.data.message);
            fetchData();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Error al inicializar');
        }
    };

    const getRoleLabel = (role) => {
        const labels = {
            agent: 'Agente',
            coordinator: 'Coordinador',
            executive: 'Ejecutivo',
        };
        return labels[role] || role;
    };

    const getRoleBadgeColor = (role) => {
        const colors = {
            agent: 'bg-emerald-100 text-emerald-700',
            coordinator: 'bg-blue-100 text-blue-700',
            executive: 'bg-slate-100 text-slate-700',
        };
        return colors[role] || 'bg-slate-100 text-slate-700';
    };

    if (!isCoordinator()) {
        return (
            <div className="text-center py-16">
                <Shield className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-700 mb-2">
                    Acceso restringido
                </h3>
                <p className="text-slate-500">
                    Solo los coordinadores pueden acceder a la configuración
                </p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">
                        Configuración
                    </h1>
                    <p className="text-slate-500 text-sm">
                        Administra usuarios, clientes y proveedores
                    </p>
                </div>
                <Button variant="outline" onClick={handleSeedDatabase} data-testid="seed-btn">
                    <Database className="w-4 h-4 mr-2" />
                    Inicializar datos
                </Button>
            </div>

            {/* Password Reset Requests Alert */}
            {resetRequests.length > 0 && (
                <Card className="border-amber-200 bg-amber-50">
                    <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                            <Bell className="w-5 h-5 text-amber-600 mt-0.5" />
                            <div className="flex-1">
                                <p className="font-medium text-amber-800">
                                    Solicitudes de restablecimiento de contraseña
                                </p>
                                <div className="mt-2 space-y-2">
                                    {resetRequests.map((req) => (
                                        <div 
                                            key={req.id} 
                                            className="flex items-center justify-between bg-white p-3 rounded-sm border border-amber-200"
                                        >
                                            <div>
                                                <p className="font-medium text-slate-900">{req.user_name}</p>
                                                <p className="text-sm text-slate-500">{req.user_email}</p>
                                                <p className="text-xs text-slate-400">{formatDateTime(req.requested_at)}</p>
                                            </div>
                                            <div className="flex gap-2">
                                                <Button
                                                    size="sm"
                                                    onClick={() => handleOpenPasswordModal({ id: req.user_id, name: req.user_name })}
                                                    data-testid={`approve-reset-${req.id}`}
                                                >
                                                    <Key className="w-4 h-4 mr-1" />
                                                    Cambiar contraseña
                                                </Button>
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    onClick={() => handleDismissRequest(req.id)}
                                                    data-testid={`dismiss-reset-${req.id}`}
                                                >
                                                    <X className="w-4 h-4" />
                                                </Button>
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
                <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="users" data-testid="tab-users">
                        <Users className="w-4 h-4 mr-2" />
                        Usuarios
                    </TabsTrigger>
                    <TabsTrigger value="clients" data-testid="tab-clients">
                        <Building2 className="w-4 h-4 mr-2" />
                        Clientes
                    </TabsTrigger>
                    <TabsTrigger value="providers" data-testid="tab-providers">
                        <Truck className="w-4 h-4 mr-2" />
                        Proveedores
                    </TabsTrigger>
                </TabsList>

                {/* Users Tab */}
                <TabsContent value="users" className="space-y-4">
                    <div className="flex justify-end">
                        <Button onClick={() => handleOpenUserModal()} data-testid="add-user-btn">
                            <Plus className="w-4 h-4 mr-2" />
                            Nuevo usuario
                        </Button>
                    </div>

                    <Card>
                        <CardContent className="p-0">
                            {loading ? (
                                <div className="p-8 flex justify-center">
                                    <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
                                </div>
                            ) : users.length === 0 ? (
                                <div className="text-center py-12">
                                    <Users className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                                    <p className="text-slate-500">No hay usuarios registrados</p>
                                </div>
                            ) : (
                                <table className="data-table w-full">
                                    <thead>
                                        <tr>
                                            <th>Nombre</th>
                                            <th>Email</th>
                                            <th>Rol</th>
                                            <th>Asignaciones</th>
                                            <th>Acciones</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {users.map((user) => (
                                            <tr key={user.id} data-testid={`user-row-${user.id}`}>
                                                <td className="font-medium">{user.name}</td>
                                                <td className="text-slate-600">{user.email}</td>
                                                <td>
                                                    <span className={`px-2 py-1 text-xs font-medium rounded ${getRoleBadgeColor(user.role)}`}>
                                                        {getRoleLabel(user.role)}
                                                    </span>
                                                </td>
                                                <td>
                                                    <div className="flex flex-wrap gap-1">
                                                        {(user.assigned_client_names || []).map((name, i) => (
                                                            <span key={`c-${i}`} className="px-1.5 py-0.5 text-xs bg-blue-50 text-blue-700 rounded">
                                                                {name}
                                                            </span>
                                                        ))}
                                                        {(user.assigned_provider_names || []).map((name, i) => (
                                                            <span key={`p-${i}`} className="px-1.5 py-0.5 text-xs bg-emerald-50 text-emerald-700 rounded">
                                                                {name}
                                                            </span>
                                                        ))}
                                                        {!(user.assigned_client_names?.length || user.assigned_provider_names?.length) && (
                                                            <span className="text-xs text-slate-400">Sin asignar</span>
                                                        )}
                                                    </div>
                                                </td>
                                                <td>
                                                    <div className="flex items-center gap-1">
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            onClick={() => handleOpenAssignmentModal(user)}
                                                            data-testid={`assign-user-${user.id}`}
                                                            title="Asignaciones"
                                                        >
                                                            <LinkIcon className="w-4 h-4" />
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            onClick={() => handleOpenUserModal(user)}
                                                            data-testid={`edit-user-${user.id}`}
                                                        >
                                                            <Pencil className="w-4 h-4" />
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            onClick={() => handleOpenPasswordModal(user)}
                                                            data-testid={`password-user-${user.id}`}
                                                        >
                                                            <Key className="w-4 h-4" />
                                                        </Button>
                                                        <Button
                                                            variant="ghost"
                                                            size="icon"
                                                            className="text-red-600"
                                                            onClick={() => {
                                                                setDeleteTarget(user);
                                                                setDeleteType('user');
                                                                setShowDeleteConfirm(true);
                                                            }}
                                                            data-testid={`delete-user-${user.id}`}
                                                        >
                                                            <Trash2 className="w-4 h-4" />
                                                        </Button>
                                                    </div>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Clients Tab */}
                <TabsContent value="clients" className="space-y-4">
                    <div className="flex justify-end">
                        <Button onClick={() => handleOpenEntityModal('client')} data-testid="add-client-btn">
                            <Plus className="w-4 h-4 mr-2" />
                            Nuevo cliente
                        </Button>
                    </div>

                    <Card>
                        <CardContent className="p-0">
                            {loading ? (
                                <div className="p-8 flex justify-center">
                                    <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
                                </div>
                            ) : clients.length === 0 ? (
                                <div className="text-center py-12">
                                    <Building2 className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                                    <p className="text-slate-500">No hay clientes registrados</p>
                                </div>
                            ) : (
                                <table className="data-table w-full">
                                    <thead>
                                        <tr>
                                            <th>Nombre</th>
                                            <th>ID</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {clients.map((client) => (
                                            <tr key={client.id} data-testid={`client-row-${client.id}`}>
                                                <td className="font-medium">{client.name}</td>
                                                <td className="font-mono text-xs text-slate-500">{client.id}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Providers Tab */}
                <TabsContent value="providers" className="space-y-4">
                    <div className="flex justify-end">
                        <Button onClick={() => handleOpenEntityModal('provider')} data-testid="add-provider-btn">
                            <Plus className="w-4 h-4 mr-2" />
                            Nuevo proveedor
                        </Button>
                    </div>

                    <Card>
                        <CardContent className="p-0">
                            {loading ? (
                                <div className="p-8 flex justify-center">
                                    <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
                                </div>
                            ) : providers.length === 0 ? (
                                <div className="text-center py-12">
                                    <Truck className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                                    <p className="text-slate-500">No hay proveedores registrados</p>
                                </div>
                            ) : (
                                <table className="data-table w-full">
                                    <thead>
                                        <tr>
                                            <th>Nombre</th>
                                            <th>Contacto</th>
                                            <th>Teléfono</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {providers.map((provider) => (
                                            <tr key={provider.id} data-testid={`provider-row-${provider.id}`}>
                                                <td className="font-medium">{provider.name}</td>
                                                <td className="text-slate-600">{provider.contact_name || '-'}</td>
                                                <td className="font-mono text-sm">{provider.contact_phone || '-'}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>

            {/* User Modal */}
            <Dialog open={showUserModal} onOpenChange={setShowUserModal}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle className="font-heading">
                            {editingUser ? 'Editar usuario' : 'Nuevo usuario'}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label>Nombre *</Label>
                            <Input
                                value={userForm.name}
                                onChange={(e) => setUserForm({ ...userForm, name: e.target.value })}
                                placeholder="Juan Pérez"
                                data-testid="user-name-input"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Correo electrónico *</Label>
                            <Input
                                type="email"
                                value={userForm.email}
                                onChange={(e) => setUserForm({ ...userForm, email: e.target.value })}
                                placeholder="juan@empresa.com"
                                data-testid="user-email-input"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Rol *</Label>
                            <Select
                                value={userForm.role}
                                onValueChange={(v) => setUserForm({ ...userForm, role: v })}
                            >
                                <SelectTrigger data-testid="user-role-select">
                                    <SelectValue placeholder="Seleccionar rol" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="agent">Agente</SelectItem>
                                    <SelectItem value="coordinator">Coordinador</SelectItem>
                                    <SelectItem value="executive">Ejecutivo</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        {!editingUser && (
                            <div className="space-y-2">
                                <Label>Contraseña *</Label>
                                <Input
                                    type="password"
                                    value={userForm.password}
                                    onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
                                    placeholder="••••••••"
                                    data-testid="user-password-input"
                                />
                            </div>
                        )}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowUserModal(false)}>
                            Cancelar
                        </Button>
                        <Button onClick={handleSaveUser} disabled={userSubmitting} data-testid="save-user-btn">
                            {userSubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            {editingUser ? 'Actualizar' : 'Crear'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Password Modal */}
            <Dialog open={showPasswordModal} onOpenChange={setShowPasswordModal}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle className="font-heading">Cambiar contraseña</DialogTitle>
                        <DialogDescription>
                            Establecer nueva contraseña para {passwordUser?.name}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label>Nueva contraseña</Label>
                            <Input
                                type="password"
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                placeholder="••••••••"
                                data-testid="new-password-input"
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowPasswordModal(false)}>
                            Cancelar
                        </Button>
                        <Button onClick={handleChangePassword} disabled={passwordSubmitting} data-testid="change-password-btn">
                            {passwordSubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            Cambiar contraseña
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Entity Modal */}
            <Dialog open={showEntityModal} onOpenChange={setShowEntityModal}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle className="font-heading">
                            Nuevo {entityType === 'client' ? 'cliente' : 'proveedor'}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label>Nombre *</Label>
                            <Input
                                value={entityForm.name}
                                onChange={(e) => setEntityForm({ ...entityForm, name: e.target.value })}
                                placeholder={entityType === 'client' ? 'Empresa ABC' : 'Logística XYZ'}
                                data-testid="entity-name-input"
                            />
                        </div>
                        {entityType === 'provider' && (
                            <>
                                <div className="space-y-2">
                                    <Label>Nombre de contacto</Label>
                                    <Input
                                        value={entityForm.contact_name}
                                        onChange={(e) => setEntityForm({ ...entityForm, contact_name: e.target.value })}
                                        placeholder="Juan Pérez"
                                        data-testid="entity-contact-input"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Teléfono de contacto</Label>
                                    <Input
                                        value={entityForm.contact_phone}
                                        onChange={(e) => setEntityForm({ ...entityForm, contact_phone: e.target.value })}
                                        placeholder="+52 55 1234 5678"
                                        data-testid="entity-phone-input"
                                    />
                                </div>
                            </>
                        )}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowEntityModal(false)}>
                            Cancelar
                        </Button>
                        <Button onClick={handleSaveEntity} disabled={entitySubmitting} data-testid="save-entity-btn">
                            {entitySubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            Crear
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Assignment Modal */}
            <Dialog open={showAssignmentModal} onOpenChange={setShowAssignmentModal}>
                <DialogContent className="max-w-lg">
                    <DialogHeader>
                        <DialogTitle className="font-heading">
                            Asignaciones de {assignmentUser?.name}
                        </DialogTitle>
                        <DialogDescription>
                            Selecciona los clientes y proveedores asignados a este usuario
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-6">
                        <div className="space-y-3">
                            <Label className="font-medium">Clientes asignados</Label>
                            {clients.length === 0 ? (
                                <p className="text-sm text-slate-500">No hay clientes registrados</p>
                            ) : (
                                <div className="space-y-2 max-h-40 overflow-y-auto">
                                    {clients.map((client) => (
                                        <div key={client.id} className="flex items-center space-x-3">
                                            <Checkbox
                                                id={`assign-client-${client.id}`}
                                                checked={userAssignments.assigned_clients.includes(client.id)}
                                                onCheckedChange={() => toggleClientAssignment(client.id)}
                                                data-testid={`assign-client-${client.id}`}
                                            />
                                            <label htmlFor={`assign-client-${client.id}`} className="text-sm text-slate-700 cursor-pointer">
                                                {client.name}
                                            </label>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                        <div className="space-y-3">
                            <Label className="font-medium">Proveedores asignados</Label>
                            {providers.length === 0 ? (
                                <p className="text-sm text-slate-500">No hay proveedores registrados</p>
                            ) : (
                                <div className="space-y-2 max-h-40 overflow-y-auto">
                                    {providers.map((provider) => (
                                        <div key={provider.id} className="flex items-center space-x-3">
                                            <Checkbox
                                                id={`assign-provider-${provider.id}`}
                                                checked={userAssignments.assigned_providers.includes(provider.id)}
                                                onCheckedChange={() => toggleProviderAssignment(provider.id)}
                                                data-testid={`assign-provider-${provider.id}`}
                                            />
                                            <label htmlFor={`assign-provider-${provider.id}`} className="text-sm text-slate-700 cursor-pointer">
                                                {provider.name}
                                            </label>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowAssignmentModal(false)}>
                            Cancelar
                        </Button>
                        <Button onClick={handleSaveAssignments} disabled={assignmentSubmitting} data-testid="save-assignments-btn">
                            {assignmentSubmitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                            Guardar asignaciones
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Delete Confirm */}
            <AlertDialog open={showDeleteConfirm} onOpenChange={setShowDeleteConfirm}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle className="font-heading">
                            ¿Eliminar {deleteType === 'user' ? 'usuario' : deleteType}?
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                            Esta acción no se puede deshacer. Se eliminará permanentemente{' '}
                            <strong>{deleteTarget?.name || deleteTarget?.email}</strong>.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>Cancelar</AlertDialogCancel>
                        <AlertDialogAction 
                            onClick={handleDeleteUser}
                            className="bg-red-600 hover:bg-red-700"
                            data-testid="confirm-delete-btn"
                        >
                            Eliminar
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </div>
    );
};

export default Settings;

import React from 'react';
import { Button } from '../ui/button';
import { Card, CardContent } from '../ui/card';
import { Input } from '../ui/input';
import { Plus, Pencil, Trash2, Key, Loader2, Users, Search, Link as LinkIcon } from 'lucide-react';

export const SettingsUsersTab = ({
    loading,
    searchUsers,
    setSearchUsers,
    sortedUsers,
    filteredUsers,
    UserSortHeader,
    getRoleBadgeColor,
    getRoleLabel,
    handleOpenUserModal,
    handleOpenAssignmentModal,
    handleOpenPasswordModal,
    onDeleteUser,
}) => (
    <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
            <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <Input
                    value={searchUsers}
                    onChange={(e) => setSearchUsers(e.target.value)}
                    placeholder="Buscar usuario..."
                    className="pl-9"
                    data-testid="search-users-input"
                />
            </div>
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
                ) : filteredUsers.length === 0 ? (
                    <div className="text-center py-12">
                        <Users className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                        <p className="text-slate-500">{searchUsers ? 'Sin resultados' : 'No hay usuarios registrados'}</p>
                    </div>
                ) : (
                    <table className="data-table w-full">
                        <thead>
                            <tr>
                                <UserSortHeader field="name">Nombre</UserSortHeader>
                                <UserSortHeader field="email">Email</UserSortHeader>
                                <UserSortHeader field="role">Rol</UserSortHeader>
                                <th>Asignaciones</th>
                                <th>Acciones</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sortedUsers.map((user) => (
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
                                                <span key={`c-${user.id}-${i}`} className="px-1.5 py-0.5 text-xs bg-blue-50 text-blue-700 rounded">
                                                    {name}
                                                </span>
                                            ))}
                                            {(user.assigned_provider_names || []).map((name, i) => (
                                                <span key={`p-${user.id}-${i}`} className="px-1.5 py-0.5 text-xs bg-emerald-50 text-emerald-700 rounded">
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
                                            <Button variant="ghost" size="icon" onClick={() => handleOpenAssignmentModal(user)} data-testid={`assign-user-${user.id}`} title="Asignaciones">
                                                <LinkIcon className="w-4 h-4" />
                                            </Button>
                                            <Button variant="ghost" size="icon" onClick={() => handleOpenUserModal(user)} data-testid={`edit-user-${user.id}`}>
                                                <Pencil className="w-4 h-4" />
                                            </Button>
                                            <Button variant="ghost" size="icon" onClick={() => handleOpenPasswordModal(user)} data-testid={`password-user-${user.id}`}>
                                                <Key className="w-4 h-4" />
                                            </Button>
                                            <Button variant="ghost" size="icon" className="text-red-600" onClick={() => onDeleteUser(user)} data-testid={`delete-user-${user.id}`}>
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
    </div>
);

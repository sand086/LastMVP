import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Truck, Eye, EyeOff, AlertCircle, Loader2 } from 'lucide-react';
import { requestPasswordReset } from '../lib/api';
import { toast } from 'sonner';

const Login = () => {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [showForgotPassword, setShowForgotPassword] = useState(false);
    const [resetEmail, setResetEmail] = useState('');
    const [resetLoading, setResetLoading] = useState(false);

    const { login } = useAuth();
    const navigate = useNavigate();

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        const result = await login(email, password);
        
        if (result.success) {
            navigate('/');
        } else {
            setError(result.error);
        }
        
        setLoading(false);
    };

    const handlePasswordReset = async (e) => {
        e.preventDefault();
        setResetLoading(true);

        try {
            await requestPasswordReset(resetEmail);
            toast.success('Solicitud enviada', {
                description: 'El administrador procesará tu solicitud de restablecimiento.',
            });
            setShowForgotPassword(false);
            setResetEmail('');
        } catch (err) {
            toast.error('Error', {
                description: 'No se pudo enviar la solicitud. Intenta de nuevo.',
            });
        }

        setResetLoading(false);
    };

    return (
        <div className="min-h-screen flex">
            {/* Left side - Image */}
            <div 
                className="hidden lg:flex lg:w-1/2 relative"
                style={{
                    backgroundImage: 'url(https://images.unsplash.com/photo-1669003154471-b72fe01a899d?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1MDV8MHwxfHNlYXJjaHwxfHxsb2dpc3RpY3MlMjB3YXJlaG91c2UlMjBhZXJpYWx8ZW58MHx8fHwxNzczNjkwNDc2fDA&ixlib=rb-4.1.0&q=85)',
                    backgroundSize: 'cover',
                    backgroundPosition: 'center',
                }}
            >
                <div className="absolute inset-0 bg-slate-900/80" />
                <div className="relative z-10 flex flex-col justify-between p-12 text-white">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-white rounded-sm flex items-center justify-center">
                            <Truck className="w-6 h-6 text-slate-900" strokeWidth={1.5} />
                        </div>
                        <div>
                            <span className="font-heading font-bold text-2xl tracking-tight">LASTMILE</span>
                            <span className="font-heading text-sm text-slate-300 block -mt-1">OS</span>
                        </div>
                    </div>
                    
                    <div>
                        <h2 className="font-heading text-4xl font-bold mb-4 tracking-tight">
                            GESTIÓN DE ÚLTIMA MILLA
                        </h2>
                        <p className="text-slate-300 text-lg max-w-md leading-relaxed">
                            Control completo de operaciones de mensajería para proveedores de transporte B2B.
                        </p>
                    </div>

                    <p className="text-slate-400 text-sm">
                        © 2026 ME - Mensajería y Estrategias
                    </p>
                </div>
            </div>

            {/* Right side - Form */}
            <div className="flex-1 flex items-center justify-center p-8 bg-[#F8FAFC]">
                <div className="w-full max-w-md">
                    {/* Mobile logo */}
                    <div className="lg:hidden flex items-center gap-3 mb-8">
                        <div className="w-10 h-10 bg-slate-900 rounded-sm flex items-center justify-center">
                            <Truck className="w-6 h-6 text-white" strokeWidth={1.5} />
                        </div>
                        <div>
                            <span className="font-heading font-bold text-2xl text-slate-900 tracking-tight">LASTMILE</span>
                            <span className="font-heading text-sm text-slate-500 block -mt-1">OS</span>
                        </div>
                    </div>

                    <div className="bg-white rounded-sm border border-slate-200 shadow-sm p-8">
                        {!showForgotPassword ? (
                            <>
                                <div className="mb-6">
                                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">
                                        Iniciar sesión
                                    </h1>
                                    <p className="text-slate-500 text-sm mt-1">
                                        Ingresa tus credenciales para continuar
                                    </p>
                                </div>

                                {error && (
                                    <Alert variant="destructive" className="mb-4">
                                        <AlertCircle className="h-4 w-4" />
                                        <AlertDescription>{error}</AlertDescription>
                                    </Alert>
                                )}

                                <form onSubmit={handleSubmit} className="space-y-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="email">Correo electrónico</Label>
                                        <Input
                                            id="email"
                                            type="email"
                                            placeholder="tu@email.com"
                                            value={email}
                                            onChange={(e) => setEmail(e.target.value)}
                                            required
                                            className="input-focus"
                                            data-testid="login-email-input"
                                        />
                                    </div>

                                    <div className="space-y-2">
                                        <Label htmlFor="password">Contraseña</Label>
                                        <div className="relative">
                                            <Input
                                                id="password"
                                                type={showPassword ? 'text' : 'password'}
                                                placeholder="••••••••"
                                                value={password}
                                                onChange={(e) => setPassword(e.target.value)}
                                                required
                                                className="input-focus pr-10"
                                                data-testid="login-password-input"
                                            />
                                            <button
                                                type="button"
                                                onClick={() => setShowPassword(!showPassword)}
                                                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                                                data-testid="toggle-password-btn"
                                            >
                                                {showPassword ? (
                                                    <EyeOff className="w-4 h-4" />
                                                ) : (
                                                    <Eye className="w-4 h-4" />
                                                )}
                                            </button>
                                        </div>
                                    </div>

                                    <Button
                                        type="submit"
                                        className="w-full bg-slate-900 hover:bg-slate-800 btn-hover"
                                        disabled={loading}
                                        data-testid="login-submit-btn"
                                    >
                                        {loading ? (
                                            <>
                                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                                Iniciando...
                                            </>
                                        ) : (
                                            'Iniciar sesión'
                                        )}
                                    </Button>
                                </form>

                                <div className="mt-4 text-center">
                                    <button
                                        type="button"
                                        onClick={() => setShowForgotPassword(true)}
                                        className="text-sm text-slate-500 hover:text-slate-700 transition-colors"
                                        data-testid="forgot-password-link"
                                    >
                                        ¿Olvidaste tu contraseña?
                                    </button>
                                </div>
                            </>
                        ) : (
                            <>
                                <div className="mb-6">
                                    <h1 className="font-heading text-2xl font-bold text-slate-900 tracking-tight">
                                        Restablecer contraseña
                                    </h1>
                                    <p className="text-slate-500 text-sm mt-1">
                                        Se enviará una solicitud al administrador
                                    </p>
                                </div>

                                <form onSubmit={handlePasswordReset} className="space-y-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="reset-email">Correo electrónico</Label>
                                        <Input
                                            id="reset-email"
                                            type="email"
                                            placeholder="tu@email.com"
                                            value={resetEmail}
                                            onChange={(e) => setResetEmail(e.target.value)}
                                            required
                                            className="input-focus"
                                            data-testid="reset-email-input"
                                        />
                                    </div>

                                    <Button
                                        type="submit"
                                        className="w-full bg-slate-900 hover:bg-slate-800 btn-hover"
                                        disabled={resetLoading}
                                        data-testid="reset-submit-btn"
                                    >
                                        {resetLoading ? (
                                            <>
                                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                                Enviando...
                                            </>
                                        ) : (
                                            'Enviar solicitud'
                                        )}
                                    </Button>
                                </form>

                                <div className="mt-4 text-center">
                                    <button
                                        type="button"
                                        onClick={() => setShowForgotPassword(false)}
                                        className="text-sm text-slate-500 hover:text-slate-700 transition-colors"
                                        data-testid="back-to-login-link"
                                    >
                                        Volver al inicio de sesión
                                    </button>
                                </div>
                            </>
                        )}
                    </div>

                    <p className="text-center text-slate-400 text-xs mt-6">
                        Credenciales de prueba: agente@me.mx / LastMile2026
                    </p>
                </div>
            </div>
        </div>
    );
};

export default Login;

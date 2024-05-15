from PIL import Image
import torch
import torch.nn.functional as Fun
import matplotlib
import numpy as np
import os


import time

import pickle
import bz2

import socket
import struct
import sys
#import pickle
import time
import random

from numba import jit

parallel_compress = False
compress_model = True
model_bytes = 'float16' # int8 # float32 # float16


# --- *** --- *** --- *** ---
# кластер
from multiprocessing import Pool
import pickle
import bz2
import time
import mgzip
import io


#import marshal as pickle
import pickle



def parallel_compress(data_2, N_processes=12):
    start_time = time.time()
    print('сжатие данных перед отправкой (функция)')
    data_2 = pickle.dumps(data_2) #, protocol=4
    print('размер данных для компрессии', len(data_2))
    #print('Время на компрессию (pickle):', time.time() - start_time)
    
    if compress_model:
        data_2 = mgzip.compress(data_2, compresslevel=1, thread=N_processes, blocksize=1000000)
    print('сжатие данных закончено, размер', len(data_2))
    #print('Время на компрессию (pickle + компрессия mgzip):', time.time() - start_time)
    return data_2

def parallel_decompress(data, N_processes=12):
    #print('декомпрессия, размер до', len(data))
    start_time = time.time()
    #print(len(data))
    print('декомпрессия, размер до', len(data))
    if compress_model:
        data = mgzip.decompress(data, thread=N_processes, blocksize=1000000)
    print('декомпрессия, размер после', len(data))
    #print('Время на декомпрессию (декомпрессия, mgzip):', time.time() - start_time)
    start_time = time.time()
    #print(len(data), data[:100])
    data = pickle.loads(data) # , fix_imports=False
    #print('Время на декомпрессию (декомпрессия + pickle):', time.time() - start_time)
    return data
# 0.9375629425048828 секунд на прием и все остальное кроме отправки назад



#@jit()
def recv_msg_conn_(self_):
    start_time = time.time()
    # Получение длины сообщения и распаковка в integer
    raw_msglen = recvall_conn(self_, 4)
    if not raw_msglen:
        return None
    msglen = struct.unpack('>I', raw_msglen)[0]
    # Получение данных
    msg = recvall_conn(self_, msglen)
    
    #print('Время на декомпрессию при приеме (прием):', time.time() - start_time)
    
    # декомпрессия
    msg = parallel_decompress(msg)
    
    #print('Время на декомпрессию при приеме (прием + decompress):', time.time() - start_time)
    return msg

#@jit()
def recvall_conn(self_, n):
    # Функция для получения n байт или возврата None если получен EOF
    data = b''
    while len(data) < n:
        packet = self_._conn.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data


class SuperSocket():
    def __init__(self, sock, conn):
        self._sock = sock
        self._conn = conn

    def send_msg_serv(self, msg):
        start_time = time.time()
        
        print('сжатие данных перед отправкой')
        # сжатие
        bmsg = parallel_compress(msg)
        print('сжатие данных завершено, время:', time.time() - start_time)
        
        # Каждое сообщение будет иметь префикс в 4 байта блинной(network byte order)
        bmsg = struct.pack('>I', len(bmsg)) + bmsg
        self._sock.sendall(bmsg)
    
    def send_msg_conn(self, msg):
        bmsg = parallel_compress(msg)
        #bmsg = pickle.dumps(msg)
        #bmsg = bz2.compress(bmsg, compresslevel=1)
        #print(len(bmsg))
        
        # Каждое сообщение будет иметь префикс в 4 байта блинной(network byte order)
        bmsg = struct.pack('>I', len(bmsg)) + bmsg
        self._conn.sendall(bmsg)

    def recv_msg_conn(self):
        return recv_msg_conn_(self)
    
    def recv_msg_serv(self):
        # Получение длины сообщения и распаковка в integer
        raw_msglen = self.recvall_serv(4)
        if not raw_msglen:
            return None
        msglen = struct.unpack('>I', raw_msglen)[0]
        # Получение данных
        msg = self.recvall_serv(msglen)
        
        msg = parallel_decompress(msg)
        #msg = bz2.decompress(msg)
        #return pickle.loads(msg)
        return msg

    def recvall_conn(self, n):
        # Функция для получения n байт или возврата None если получен EOF
        data = b''
        while len(data) < n:
            packet = self._conn.recv(n - len(data))
            if not packet:
                return None
            data += packet
        return data
    
    def recvall_serv(self, n):
        # Функция для получения n байт или возврата None если получен EOF
        data = b''
        while len(data) < n:
            packet = self._sock.recv(n - len(data))
            if not packet:
                return None
            data += packet
        return data
    
    def close(self):
        return self._sock.close()

# функция создания сервера
def create_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    ip = "109.123.171.39" # socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port = 5005
    sock.bind((ip, port))
    
    # сервер ожидает передачи информации
    sock.listen(N_conn)
    
    sup_sock_all = []
    for i in range(N_conn):
        # начинаем принимать соединения
        conn, addr = sock.accept()
        sup_sock = SuperSocket(sock, conn)
        sup_sock_all.append(sup_sock)
        print('Подключен клиент')
    
    return sup_sock_all

# функция создания рабочего
def create_worker():
    ip = "109.123.171.39"
    port = 5005

    # создаём сокет для подключения
    sock = socket.socket()
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sock.connect((ip,port))
    #sock.setblocking(True)
    
    sup_sock = SuperSocket(sock, None)
    
    return sup_sock


# отправить сообщение всем ПК в кластере
def serv_send_all_pc(sup_sock_all, msg):
    for i in range(len(sup_sock_all)):
        sup_sock_all[i].send_msg_conn(msg)

# принять сообщение от всех ПК в кластере
def serv_recv_all_pc(sup_sock_all):
    msg = []
    for i in range(len(sup_sock_all)):
        msg_recv = sup_sock_all[i].recv_msg_conn()
        msg.append(msg_recv)
    return msg


N_conn = 1 # количество ПК в кластере подключенных к серверу (без учета сервера)

# имена компьютеров и их ID
name_id_computers = {
    'W09013' : 0,
    'W09012' : 1,
    'W09010' : 2,
    'W09005' : 3,
    'W09006' : 4,
    'W09007' : 5
    }

# соответствие ID и IP адресов PC
id_ip_computers = {
    0 : '109.123.171.39',
    1 : '109.123.171.38',
    2 : '109.123.171.36',
    3 : '109.123.171.31',
    4 : '109.123.171.32',
    5 : '109.123.171.33'
    }



# присваиваем ID программе
name_com = socket.gethostname()
com_id = name_id_computers[name_com]

print('ID компьютера:', com_id)



def grad_serv_mean(network, sock_all, optimizer, print_flag = False):
    #print('\n\n\nПРИЕМ ДАННЫХ:')
    #print('Эпоха: ', _, 'it', it, 'i', i)
    start_time = time.time()
    print('отправка модели')
    
    # *** --- *** --- *** --- ***
    # ПРИЕМ СЕРВЕРОМ ГРАДИЕНТОВ ОТ ДРУГИХ ПК
    # загрузка моделей
    models_grads = serv_recv_all_pc(sock_all)
    print('Время передачи данных (скачивание модели):', time.time() - start_time)
    
    start_time_grad = time.time()
    # кривое усреднение/объединение моделей (поправить!)
    for n_model in range(len(models_grads)):
        grad_torch = models_grads[n_model]
        if model_bytes == 'int8':
            #print('grad_torch[0]', grad_torch[0])
            max_grad = grad_torch[0]
            grad_torch = grad_torch[1]
        elif model_bytes == 'float16':
            #print('grad_torch[0]', grad_torch[0])
            max_grad = grad_torch[0]
            grad_torch = grad_torch[1]
        
        #time.sleep(1)
        #print('n_model:', n_model, 'max_grad:', max_grad)
        #print(len(models_grads))
        #paral_grads = []
        #for param, grad_layer in zip(network.parameters(), grad_torch):
        #    print('Градиент:', torch.round((torch.from_numpy(np.frombuffer(grad_layer, dtype='int8')).cuda().to(torch.float32).reshape(param.grad.shape) / 100 * max_grad), decimals=2))
        #    break
        start_time_grad_for = time.time()
        if model_bytes == 'float16' or model_bytes == 'int8':
            # уменьшаем градиенты в зависимости от числа моделей
            for param, grad_layer in zip(network.parameters(), grad_torch):
                param.grad = param.grad / len(models_grads)
        
        
        
        for param, grad_layer in zip(network.parameters(), grad_torch):
            #paral_grads.append([param, grad_layer, max_grad])
            if model_bytes == 'int8':
                #grad_layer = torch.load(io.BytesIO(grad_layer))
                #grad_layer = torch.from_numpy(grad_layer).cuda()
                #np.frombuffer(grad_layer, dtype='int8')
                #param.grad = (param.grad + torch.from_numpy(np.array(np.frombuffer(grad_layer, dtype='int8').reshape(param.grad.shape), dtype='float32')).cuda() / 10 * max_grad) / 2
                # .to(torch.float32)
                #if param.grad == None:
                param.grad = (param.grad + (torch.from_numpy(np.frombuffer(grad_layer, dtype='int8')).cuda().to(torch.float32).reshape(param.size()) / 10 * max_grad) / len(models_grads))
                #else:
                #    param.grad = (param.grad + (torch.from_numpy(np.frombuffer(grad_layer, dtype='int8')).cuda().to(torch.float32).reshape(param.size()) / 100 * max_grad) / len(models_grads))               
                #print(torch.from_numpy(np.frombuffer(grad_layer, dtype='int8')).cuda().to(torch.float32).reshape(param.grad.shape))
                #print(max_grad)
                #param.grad = ((param.grad.cpu() + torch.from_numpy(np.frombuffer(grad_layer, dtype='int8')).to(torch.float32).reshape(param.grad.shape) / 10 * max_grad) / 2).cuda()               
                #pass
                #exit()
            elif model_bytes == 'float16':
                param.grad = (param.grad + (torch.from_numpy(np.frombuffer(grad_layer, dtype='float16')).cuda().to(torch.float32).reshape(param.size()) / 100 * max_grad) / len(models_grads))
            else:
                param.grad = 0#(param.grad + grad_layer.to(torch.float32)) / 2
        #print(np.frombuffer(grad_layer, dtype='int8'))
        print('Время передачи данных (объединение градиентов, цикл):', time.time() - start_time_grad_for)
        #N_processes = 12
        #with Pool(N_processes) as pr:
        #    data_2 = pr.map(my_torch_layer, [param, grad_layer, max_grad])
    # *** --- *** --- *** --- ***
    print('Время передачи данных (объединение градиентов):', time.time() - start_time_grad)
    print('Время передачи данных (усреднение параметров):', time.time() - start_time)
    # +++ *** +++ *** +++ *** +++
    # ПЕРЕСЫЛКА ГРАДИЕНТОВ ОТ СЕРВЕРА ОСТАЛЬНЫМ ПК
    start = time.time()
    # берем градиенты
    max_grad = float('-inf')
    model_grads = []
    for param in network.parameters():
        if model_bytes == 'float32':
            model_grads.append(param.grad) # (param.grad*10).to(torch.int8)) # (param.grad*100).to(torch.int8))
        elif model_bytes == 'float16':
            if max_grad < torch.max(torch.abs(param.grad)):
                max_grad = torch.max(torch.abs(param.grad))
            model_grads.append(param.grad)
        elif model_bytes == 'int8':
            if max_grad < torch.max(torch.abs(param.grad)):
                max_grad = torch.max(torch.abs(param.grad))
            model_grads.append(param.grad)
        else:
            print('НЕВЕРНЫЙ ПАРАМЕТР!!!')
    #print()
    #print(max_grad)
    if model_bytes == 'int8' and max_grad != 0:
        
        #for grads in model_grads:
        #    print('Градиент:', torch.round(grads, decimals=2))
        #    break
        
        
        model_grads_2 = []
        for i in range(len(model_grads)):
            model_grads[i] = torch.round(model_grads[i] / max_grad * 10).to(torch.int8)#.to(torch.int8).to(torch.float16)
            #buff = io.BytesIO()
            #torch.save(model_grads[i], buff)
            #model_grads_2.append(buff.getvalue())
            model_grads_2.append(model_grads[i].cpu().numpy().tobytes())
            #print('слой:', i, type(model_grads_2[i]), len(model_grads_2[i]))
        #model_grads = model_grads_2
        
        

        
        #print('max_grad', float(max_grad.detach().cpu().numpy()))
        model_grads_3 = [float(max_grad.detach().cpu().numpy()), model_grads_2]
    elif model_bytes == 'float16' and max_grad != 0:
        #for grads in model_grads:
        #    print('Градиент:', torch.round(grads, decimals=2))
        #    break
        
        
        model_grads_2 = []
        for i in range(len(model_grads)):
            model_grads[i] = torch.round(model_grads[i] / max_grad * 100).to(torch.float16)#.to(torch.int8).to(torch.float16)
            #buff = io.BytesIO()
            #torch.save(model_grads[i], buff)
            #model_grads_2.append(buff.getvalue())
            model_grads_2.append(model_grads[i].cpu().numpy().tobytes())
            #print('слой:', i, type(model_grads_2[i]), len(model_grads_2[i]))
        #model_grads = model_grads_2
        
        

        
        #print('max_grad', float(max_grad.detach().cpu().numpy()))
        model_grads_3 = [float(max_grad.detach().cpu().numpy()), model_grads_2]
    print('ПЕРЕСЫЛКА ГРАДИЕНТОВ ОТ СЕРВЕРА ОСТАЛЬНЫМ ПК', time.time() - start)
    print('усечение градиентов, время', time.time() - start_time)
    
    # пересылка модели на сервер
    # buff = io.BytesIO()
    # torch.save(model_grads, buff)
    
    start = time.time()
    serv_send_all_pc(sock_all, model_grads_3)
    print('Градиенты переданы, время:', time.time() - start)
    # +++ *** +++ *** +++ *** +++
    
    
    
    # *** --- *** --- ***
    # СИНХРОНИЗАЦИЯ ЧТОБЫ ВСЕ БЫЛО КАК НА КЛИЕНТАХ
    start = time.time()
    grad_torch = model_grads_3
    if model_bytes == 'int8':
        max_grad = grad_torch[0]
        grad_torch = grad_torch[1]
    elif model_bytes == 'float16':
        max_grad = grad_torch[0]
        grad_torch = grad_torch[1]
    
    #time.sleep(1)
    #print(len(models_grads))
    #paral_grads = []
    start_time_grad_for = time.time()
    for param, grad_layer in zip(network.parameters(), grad_torch):
        #paral_grads.append([param, grad_layer, max_grad])
        if model_bytes == 'int8':
            #grad_layer = torch.load(io.BytesIO(grad_layer))
            #grad_layer = torch.from_numpy(grad_layer).cuda()
            #np.frombuffer(grad_layer, dtype='int8')
            #param.grad = (param.grad + torch.from_numpy(np.array(np.frombuffer(grad_layer, dtype='int8').reshape(param.grad.shape), dtype='float32')).cuda() / 10 * max_grad) / 2
            # .to(torch.float32)
            #print('int8')
            param.grad = (torch.from_numpy(np.frombuffer(grad_layer, dtype='int8')).cuda().to(torch.float32).reshape(param.grad.shape) / 10 * max_grad).to(torch.float32)      
            #param.grad = ((param.grad.cpu() + torch.from_numpy(np.frombuffer(grad_layer, dtype='int8')).to(torch.float32).reshape(param.grad.shape) / 10 * max_grad) / 2).cuda()               
            #pass
        elif model_bytes == 'float16':
            param.grad = (torch.from_numpy(np.frombuffer(grad_layer, dtype='float16')).cuda().to(torch.float32).reshape(param.grad.shape) / 100 * max_grad).to(torch.float32)
        else:
            param.grad = 0#(param.grad + grad_layer.to(torch.float32)) / 2
    # *** --- *** --- ***
    
    if print_flag:
        print(param.grad)
    optimizer.step()
    optimizer.zero_grad()
    
    print('СИНХРОНИЗАЦИЯ ЧТОБЫ ВСЕ БЫЛО КАК НА КЛИЕНТАХ', time.time() - start)


def grad_client_mean(network, sock, optimizer, print_flag=False):
    #print('\n\n\nВремя вычисления на GPU:', time.time() - last_time)
    #print('Эпоха: ', _, 'it', it, 'i', i)
    start = time.time()
    # *** --- *** --- ***
    #print('\n\n\nСИНХРОНИЗАЦИЯ ДАННЫХ')
    # ПЕРЕСЫЛКА ГРАДИЕНТОВ НА СЕРВЕР
    # берем градиенты
    max_grad = float('-inf')
    model_grads = []
    for param in network.parameters():
        if model_bytes == 'float32':
            model_grads.append(param.grad) # (param.grad*10).to(torch.int8)) # (param.grad*100).to(torch.int8))
        elif model_bytes == 'float16':
            if max_grad < torch.max(torch.abs(param.grad)):
                max_grad = torch.max(torch.abs(param.grad))
            model_grads.append(param.grad)
        elif model_bytes == 'int8':
            if max_grad < torch.max(torch.abs(param.grad)):
                max_grad = torch.max(torch.abs(param.grad))
            model_grads.append(param.grad)
        else:
            print('НЕВЕРНЫЙ ПАРАМЕТР!!!')
    #print()
    #print(max_grad)
    #for grads in model_grads:
    #    print('Градиент:', torch.round(grads, decimals=2))
    #    break
    if model_bytes == 'int8' and max_grad != 0:
        model_grads_2 = []
        for i in range(len(model_grads)):
            model_grads[i] = torch.round(model_grads[i] / max_grad * 10).to(torch.int8)#.to(torch.int8).to(torch.float16)
            #buff = io.BytesIO()
            #torch.save(model_grads[i], buff)
            #model_grads_2.append(buff.getvalue())
            model_grads_2.append(model_grads[i].cpu().numpy().tobytes())
            #print('слой:', i, type(model_grads_2[i]), len(model_grads_2[i]))
        #model_grads = model_grads_2
        #print(model_grads[i].cpu().numpy())
        #print('max_grad', float(max_grad.detach().cpu().numpy()))
        model_grads_3 = [float(max_grad.detach().cpu().numpy()), model_grads_2]
    elif model_bytes == 'float16' and max_grad != 0:
        model_grads_2 = []
        for i in range(len(model_grads)):
            model_grads[i] = torch.round(model_grads[i] / max_grad * 100).to(torch.float16)#.to(torch.int8).to(torch.float16)
            #buff = io.BytesIO()
            #torch.save(model_grads[i], buff)
            #model_grads_2.append(buff.getvalue())
            model_grads_2.append(model_grads[i].cpu().numpy().tobytes())
            #print('слой:', i, type(model_grads_2[i]), len(model_grads_2[i]))
        #model_grads = model_grads_2
        #print(model_grads[i].cpu().numpy())
        #print('max_grad', float(max_grad.detach().cpu().numpy()))
        model_grads_3 = [float(max_grad.detach().cpu().numpy()), model_grads_2]
    print('усечение градиентов, время', time.time() - start)
    
    # пересылка модели на сервер
    # buff = io.BytesIO()
    # torch.save(model_grads, buff)
    
    sock.send_msg_serv(model_grads_3)
    print('Градиенты переданы, время:', time.time() - start)
    # *** --- *** --- ***
    
    
    
    # +++ *** +++ *** +++
    # ПРИЕМ ГРАДИЕНТОВ С СЕРВЕРА
    print('Прием данных от сервера:')
    grad_torch = sock.recv_msg_serv()
    if model_bytes == 'int8':
        max_grad = grad_torch[0]
        grad_torch = grad_torch[1]
    elif model_bytes == 'float16':
        max_grad = grad_torch[0]
        grad_torch = grad_torch[1]
    
    #time.sleep(1)
    #print(len(models_grads))
    #paral_grads = []
    start_time_grad_for = time.time()
    for param, grad_layer in zip(network.parameters(), grad_torch):
        #paral_grads.append([param, grad_layer, max_grad])
        if model_bytes == 'int8':
            #grad_layer = torch.load(io.BytesIO(grad_layer))
            #grad_layer = torch.from_numpy(grad_layer).cuda()
            #np.frombuffer(grad_layer, dtype='int8')
            #param.grad = (param.grad + torch.from_numpy(np.array(np.frombuffer(grad_layer, dtype='int8').reshape(param.grad.shape), dtype='float32')).cuda() / 10 * max_grad) / 2
            # .to(torch.float32)
            #print('int8')
            param.grad = (torch.from_numpy(np.frombuffer(grad_layer, dtype='int8')).cuda().to(torch.float32).reshape(param.grad.shape) / 10 * max_grad).to(torch.float32)          
            #param.grad = ((param.grad.cpu() + torch.from_numpy(np.frombuffer(grad_layer, dtype='int8')).to(torch.float32).reshape(param.grad.shape) / 10 * max_grad) / 2).cuda()               
            #pass
        elif model_bytes == 'float16':
            #grad_layer = torch.load(io.BytesIO(grad_layer))
            #grad_layer = torch.from_numpy(grad_layer).cuda()
            #np.frombuffer(grad_layer, dtype='int8')
            #param.grad = (param.grad + torch.from_numpy(np.array(np.frombuffer(grad_layer, dtype='int8').reshape(param.grad.shape), dtype='float32')).cuda() / 10 * max_grad) / 2
            # .to(torch.float32)
            #print('int8')
            param.grad = (torch.from_numpy(np.frombuffer(grad_layer, dtype='float16')).cuda().to(torch.float32).reshape(param.grad.shape) / 100 * max_grad).to(torch.float32)
        else:
            param.grad = 0#(param.grad + grad_layer.to(torch.float32)) / 2
    #print(np.frombuffer(grad_layer, dtype='int8'))
    print('Прием данных завершен:', time.time() - start_time_grad_for)
    #print()
    # +++ *** +++ *** +++
    if print_flag:
        print(param.grad)
    optimizer.step()
    optimizer.zero_grad()
    # max_grad.detach()
    
    last_time = time.time()



def synchronization_serv_model(network, optimizer, loss, sock_all):
    serv_send_all_pc(sock_all, [network, optimizer, loss])

def synchronization_client_model(sock):
    network, optimizer, criterion = sock.recv_msg_serv()
    return network, optimizer, criterion

# --- *** --- *** --- *** ---


import torch
import torch.nn as nn
import torch.nn.functional as F


class DoubleConv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(DoubleConv, self).__init__()
        self.double_conv = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.double_conv(x)


class DownBlock(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(DownBlock, self).__init__()
        self.double_conv = DoubleConv(in_channels, out_channels)
        self.down_sample = nn.MaxPool2d(2)

    def forward(self, x):
        skip_out = self.double_conv(x)
        down_out = self.down_sample(skip_out)
        return (down_out, skip_out)


class UpBlock(nn.Module):
    def __init__(self, in_channels, out_channels, up_sample_mode):
        super(UpBlock, self).__init__()
        if up_sample_mode == 'conv_transpose':
            self.up_sample = nn.ConvTranspose2d(in_channels-out_channels, in_channels-out_channels, kernel_size=2, stride=2)
        elif up_sample_mode == 'bilinear':
            self.up_sample = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
        else:
            raise ValueError("Unsupported `up_sample_mode` (can take one of `conv_transpose` or `bilinear`)")
        self.double_conv = DoubleConv(in_channels, out_channels)

    def forward(self, down_input, skip_input):
        x = self.up_sample(down_input)
        x = torch.cat([x, skip_input], dim=1)
        return self.double_conv(x)


class UNet(nn.Module):
    def __init__(self, out_classes=2, up_sample_mode='conv_transpose'):
        super(UNet, self).__init__()
        self.up_sample_mode = up_sample_mode

        N = NN_in_model
        # Downsampling Path
        self.down_conv1 = DownBlock(3, 64//N)
        self.down_conv2 = DownBlock(64//N, 128//N)
        self.down_conv3 = DownBlock(128//N, 256//N)
        self.down_conv4 = DownBlock(256//N, 512//N)
        self.down_conv5 = DownBlock(512//N, 512//N)
        # Bottleneck
        self.double_conv = DoubleConv(512//N, 512//N)
        # Upsampling Path
        self.up_conv5 = UpBlock(512//N + 512//N, 512//N, self.up_sample_mode)
        self.up_conv4 = UpBlock(512//N + 512//N, 512//N, self.up_sample_mode)
        self.up_conv3 = UpBlock(256//N + 512//N, 256//N, self.up_sample_mode)
        self.up_conv2 = UpBlock(128//N + 256//N, 128//N, self.up_sample_mode)
        self.up_conv1 = UpBlock(128//N + 64//N, 64//N, self.up_sample_mode)
        # Final Convolution
        self.conv_last = nn.Conv2d(64//N, out_classes, kernel_size=1)

    def forward(self, x):
        x, skip1_out = self.down_conv1(x)
        x, skip2_out = self.down_conv2(x)
        x, skip3_out = self.down_conv3(x)
        x, skip4_out = self.down_conv4(x)
        x, skip5_out = self.down_conv5(x)
        x = self.double_conv(x)
        x = self.up_conv5(x, skip5_out)
        x = self.up_conv4(x, skip4_out)
        x = self.up_conv3(x, skip3_out)
        x = self.up_conv2(x, skip2_out)
        x = self.up_conv1(x, skip1_out)
        x = self.conv_last(x)
        return x



import imageio as iio
def load_files(path):
  x_train = []
  y_train = []
  for file_name in sorted(os.listdir(path)):
    if '.npy' in file_name:
      y_train.append(np.load(path + file_name))
    else:
      x_train.append(iio.imread(path + file_name))

  x_train, y_train = np.array(x_train), np.array(y_train, dtype='uint8')

  x_test, y_test = x_train[-30:], y_train[-30:]
  x_train, y_train = x_train[:-30], y_train[:-30]
  return x_train, y_train, x_test, y_test





import torch
import torch.nn as nn
import torch.nn.functional as F


frequency_sending_gradients = 50
batch_size = 1
NN_in_model = 2


if com_id == 0:
    # *** --- *** --- ***
    # SERVER
    # создание сервера
    sock_all = create_server()
    # *** --- *** --- ***
    


    torch.cuda.empty_cache()

    # Get UNet model
    model = UNet(out_classes=6).cuda()
    criterion = nn.CrossEntropyLoss().cuda()
    optimizer = torch.optim.Adam(model.parameters())
    
    
    # синхронизация модели
    synchronization_serv_model(model, optimizer, criterion, sock_all)
    # *** --- *** --- ***


    
    
    
    with open(f"C:/Users/nak64/Desktop/Набор данных/Vaihingen/otus_{model_bytes}.txt", "w") as file:
        file.write(' '.join(map(str, ['\nbatch_size на одном ПК:', batch_size, "\nОбщий размер batch_size (все ПК):", batch_size*(N_conn+1), '\nЧастота передачи данных (градиентов):', frequency_sending_gradients, '\nделитель размер сети:', NN_in_model, '\nколичество ПК (включая сервер)', N_conn+1, '\n\n'])))
    
    
    optimizer.zero_grad()
    for _ in range(100):
      print('\n\n\nEpochs:', _)
      indxs = list(range(127))
      np.random.shuffle(indxs)
      for ep in range(1):
          print('\n\n\nep:', ep)
          start_time_200 = time.time()
          start_indx=127*ep
          end_indx=127*(ep+1)
          
          #X_train = download_data("C:/Users/nak64/Desktop/Набор данных/GTA 5/images/", start_indx=start_indx, end_indx=end_indx)
          #Y_train = download_data("C:/Users/nak64/Desktop/Набор данных/GTA 5/labels/", start_indx=start_indx, end_indx=end_indx)
          X_train, Y_train, X_test, Y_test = load_files("C:/Users/nak64/Desktop/Набор данных/Vaihingen/vaihingen_train/")
          # X_test = download_data("/content/drive/MyDrive/GTA 5 (mini)/images/", start_indx=start_indx, end_indx=end_indx)
          # Y_test = download_data("/content/drive/MyDrive/GTA 5 (mini)/labels/", start_indx=start_indx, end_indx=end_indx)
          
          
          X_train_pred = torch.from_numpy(np.array(X_train, dtype='float32').reshape([end_indx - start_indx, 512, 512, 3])/255).swapaxes(1, 3).swapaxes(2, 3)
          # X_test_pred = torch.from_numpy(np.array(X_test, dtype='float32').reshape([end_indx - start_indx, 512, 512, 3])/255).swapaxes(1, 3)
          
          
          Y_train_pred = torch.from_numpy(np.array(Y_train, dtype='int64'))
          # Y_test_pred = torch.from_numpy(np.array(Y_test, dtype='int64'))
          
          start_time_bt = time.time()
          start_time_bt_2 = time.time()
          mean_loss = 0
          mean_accuracy = 0
          it = 0
          num_bt = 0
          for i in range(0, len(X_train_pred), batch_size):
            it += 1
            #if it%5 != 4:
            print('img', i)
            outputs = model(X_train_pred[i:i+batch_size].cuda())
            loss = criterion(outputs, Y_train_pred[i:i+batch_size].cuda())
            loss.backward()
            
            
            if it%frequency_sending_gradients == 0:
                start_time = time.time()
                # *** --- *** --- ***
                # объединение данных на сервере
                grad_serv_mean(model, sock_all, optimizer)
                # *** --- *** --- ***
                print('Время синхронизации:', time.time() - start_time)
                optimizer.zero_grad()
                print('Время на батч:', time.time() - start_time_bt, time.time() - start_time_bt_2)
                bt_time_from_file = time.time() - start_time_bt # время на батч для файла
                num_bt += 1
                start_time_bt_2 = time.time()
            
            #loss.backward() # уже есть в grad_serv_mean
            #optimizer.step()
    
            mean_accuracy += (torch.argmax(outputs, axis=1) == Y_train_pred[i:i+batch_size].cuda()).detach().cpu().numpy().mean()
            mean_loss += loss.data.detach().cpu().numpy()
          print('mean_loss', mean_loss/it, 'mean_accuracy', mean_accuracy/it)
          print('время на 200 примеров', time.time() - start_time_200)
    
    
          with open(f"C:/Users/nak64/Desktop/Набор данных/Vaihingen/otus_{model_bytes}.txt", "a") as file:
              file.write(' '.join(map(str, ['\nep:', _, 'mean_loss', mean_loss/it, 'mean_accuracy', mean_accuracy/it, 'время на все примеры эпохи', time.time() - start_time_200, 'общее время', time.time() - start_time_200, 'среднее время на батч:', bt_time_from_file/num_bt, '\n'])))
    
    
          path =  r'C:/Users/nak64/Desktop/Набор данных/Vaihingen/model/'
          for i in range(5):
              outputs = np.argmax(model(X_train_pred[i:i+1].cuda()).detach().cpu().numpy(), axis=1)
              matplotlib.pyplot.imsave(path + f'Model {i}.png', np.uint8(outputs[0]*5))
              matplotlib.pyplot.imsave(path + f'Label {i}.png', np.uint8(Y_train_pred[i].numpy()*5))
              Image.fromarray(np.uint8(X_train_pred[i].numpy().swapaxes(1, 2).swapaxes(0, 2)*255)).save(path + f'Image {i}.png')

else:
    
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    
    # *** --- *** --- ***
    # WORCER
    # создание сервера
    sock = create_worker()
    # *** --- *** --- ***
    
    
    torch.cuda.empty_cache()
    
    # *** --- *** --- ***
    # СОЗДАНИЕ МОДЕЛИ
    # синхронизация модели
    model, optimizer, criterion = synchronization_client_model(sock)
    # *** --- *** --- ***


    indxs = list(range(2500))
    np.random.shuffle(indxs)
    
    def download_data(path, start_indx=0, end_indx=1000):
      data = []
      for path_image in np.array(sorted(os.listdir(path=path)))[indxs][start_indx:end_indx]:
        image = Image.open(path + path_image) #Открываем изображение.
        #print(np.array(image)[:1024, :1024].shape)
        data.append(np.array(image)[:512, :512]) #Загружаем пиксели.
      return data











    
    optimizer.zero_grad()
    for _ in range(100):
      print('\n\n\nEpochs:', _)
      indxs = list(range(127))
      np.random.shuffle(indxs)
      for ep in range(1):
          print('\n\n\nep:', ep)
          start_time_200 = time.time()
          start_indx=127*ep
          end_indx=127*(ep+1)
          
          #X_train = download_data("C:/Users/nak64/Desktop/Набор данных/GTA 5/images/", start_indx=start_indx, end_indx=end_indx)
          #Y_train = download_data("C:/Users/nak64/Desktop/Набор данных/GTA 5/labels/", start_indx=start_indx, end_indx=end_indx)
          X_train, Y_train, X_test, Y_test = load_files("C:/Users/nak64/Desktop/Набор данных/Vaihingen/vaihingen_train/")
          # X_test = download_data("/content/drive/MyDrive/GTA 5 (mini)/images/", start_indx=start_indx, end_indx=end_indx)
          # Y_test = download_data("/content/drive/MyDrive/GTA 5 (mini)/labels/", start_indx=start_indx, end_indx=end_indx)
          
          
          X_train_pred = torch.from_numpy(np.array(X_train, dtype='float32').reshape([end_indx - start_indx, 512, 512, 3])/255).swapaxes(1, 3).swapaxes(2, 3)
          # X_test_pred = torch.from_numpy(np.array(X_test, dtype='float32').reshape([end_indx - start_indx, 512, 512, 3])/255).swapaxes(1, 3)
          
          
          Y_train_pred = torch.from_numpy(np.array(Y_train, dtype='int64'))
          # Y_test_pred = torch.from_numpy(np.array(Y_test, dtype='int64'))
    
          mean_loss = 0
          mean_accuracy = 0
          it = 0
          for i in range(0, len(X_train_pred), batch_size):
            it += 1
            print('img', i)
            outputs = model(X_train_pred[i:i+batch_size].cuda())
            loss = criterion(outputs, Y_train_pred[i:i+batch_size].cuda())
            loss.backward()
            
            
            if it%frequency_sending_gradients == 0:
                start_time = time.time()
                # *** --- *** --- ***
                # объединение данных на сервере
                grad_client_mean(model, sock, optimizer)
                # *** --- *** --- ***
                print('Время синхронизации:', time.time() - start_time)
                optimizer.zero_grad()
            
            #loss.backward() # уже есть в grad_serv_mean
            #optimizer.step()
    
            #mean_accuracy += (torch.argmax(outputs, axis=1) == Y_train_pred[i:i+batch_size].cuda()).detach().cpu().numpy().mean()
            #mean_loss += loss.data.detach().cpu().numpy()
          #print('mean_loss', mean_loss/it, 'mean_accuracy', mean_accuracy/it)
    
    
    
          path =  r'C:/Users/nak64/Desktop/Набор данных/Vaihingen/model/'
          for i in range(5):
              outputs = np.argmax(model(X_train_pred[i:i+1].cuda()).detach().cpu().numpy(), axis=1)
              matplotlib.pyplot.imsave(path + f'Model {i}.png', np.uint8(outputs[0]*5))
              matplotlib.pyplot.imsave(path + f'Label {i}.png', np.uint8(Y_train_pred[i].numpy()*5))
              Image.fromarray(np.uint8(X_train_pred[i].numpy().swapaxes(1, 2).swapaxes(0, 2)*255)).save(path + f'Image {i}.png')




